import json
import operator
import re
from collections import defaultdict
from functools import partial, reduce
from io import BytesIO
from typing import Literal, Optional, get_type_hints

import discord
from botcore.site_api import ResponseCodeError
from discord import Colour, Embed, HTTPException, Message, MessageType
from discord.ext import commands
from discord.ext.commands import BadArgument, Cog, Context, has_any_role

import bot
import bot.exts.filtering._ui.filter as filters_ui
from bot import constants
from bot.bot import Bot
from bot.constants import Channels, MODERATION_ROLES, Roles, Webhooks
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists import FilterList, ListType, filter_list_types, list_type_converter
from bot.exts.filtering._filter_lists.filter_list import AtomicList
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._settings import ActionSettings
from bot.exts.filtering._ui.filter import (
    build_filter_repr_dict, description_and_settings_converter, filter_serializable_overrides, populate_embed_from_dict
)
from bot.exts.filtering._ui.filter_list import FilterListAddView, FilterListEditView, settings_converter
from bot.exts.filtering._ui.search import SearchEditView, search_criteria_converter
from bot.exts.filtering._ui.ui import (
    ArgumentCompletionView, DeleteConfirmationView, build_mod_alert, format_response_error
)
from bot.exts.filtering._utils import past_tense, repr_equals, starting_value, to_serializable
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils.message_cache import MessageCache

log = get_logger(__name__)

CACHE_SIZE = 100


class Filtering(Cog):
    """Filtering and alerting for content posted on the server."""

    # A set of filter list names with missing implementations that already caused a warning.
    already_warned = set()

    # region: init

    def __init__(self, bot: Bot):
        self.bot = bot
        self.filter_lists: dict[str, FilterList] = {}
        self._subscriptions: defaultdict[Event, list[FilterList]] = defaultdict(list)
        self.webhook = None

        self.loaded_settings = {}
        self.loaded_filters = {}
        self.loaded_filter_settings = {}

        self.message_cache = MessageCache(CACHE_SIZE, newest_first=True)

    async def cog_load(self) -> None:
        """
        Fetch the filter data from the API, parse it, and load it to the appropriate data structures.

        Additionally, fetch the alerting webhook.
        """
        await self.bot.wait_until_guild_available()

        raw_filter_lists = await self.bot.api_client.get("bot/filter/filter_lists")
        example_list = None
        for raw_filter_list in raw_filter_lists:
            loaded_list = self._load_raw_filter_list(raw_filter_list)
            if not example_list and loaded_list:
                example_list = loaded_list

        try:
            self.webhook = await self.bot.fetch_webhook(Webhooks.filters)
        except HTTPException:
            log.error(f"Failed to fetch filters webhook with ID `{Webhooks.filters}`.")

        self.collect_loaded_types(example_list)

    def subscribe(self, filter_list: FilterList, *events: Event) -> None:
        """
        Subscribe a filter list to the given events.

        The filter list is added to a list for each event. When the event is triggered, the filter context will be
        dispatched to the subscribed filter lists.

        While it's possible to just make each filter list check the context's event, these are only the events a filter
        list expects to receive from the filtering cog, there isn't an actual limitation on the kinds of events a filter
        list can handle as long as the filter context is built properly. If for whatever reason we want to invoke a
        filter list outside of the usual procedure with the filtering cog, it will be more problematic if the events are
        hard-coded into each filter list.
        """
        for event in events:
            if filter_list not in self._subscriptions[event]:
                self._subscriptions[event].append(filter_list)

    def unsubscribe(self, filter_list: FilterList, *events: Event) -> None:
        """Unsubscribe a filter list from the given events. If no events given, unsubscribe from every event."""
        if not events:
            events = list(self._subscriptions)

        for event in events:
            if filter_list in self._subscriptions.get(event, []):
                self._subscriptions[event].remove(filter_list)

    def collect_loaded_types(self, example_list: AtomicList) -> None:
        """
        Go over the classes used in initialization and collect them to dictionaries.

        The information that is collected is about the types actually used to load the API response, not all types
        available in the filtering extension.

        Any filter list has the fields for all settings in the DB schema, so picking any one of them is enough.
        """
        # Get the filter types used by each filter list.
        for filter_list in self.filter_lists.values():
            self.loaded_filters.update({filter_type.name: filter_type for filter_type in filter_list.filter_types})

        # Get the setting types used by each filter list.
        if self.filter_lists:
            settings_entries = set()
            # The settings are split between actions and validations.
            for settings_group in example_list.defaults:
                settings_entries.update(type(setting) for _, setting in settings_group.items())

            for setting_entry in settings_entries:
                type_hints = get_type_hints(setting_entry)
                # The description should be either a string or a dictionary.
                if isinstance(setting_entry.description, str):
                    # If it's a string, then the settings entry matches a single field in the DB,
                    # and its name is the setting type's name attribute.
                    self.loaded_settings[setting_entry.name] = (
                        setting_entry.description, setting_entry, type_hints[setting_entry.name]
                    )
                else:
                    # Otherwise, the setting entry works with compound settings.
                    self.loaded_settings.update({
                        subsetting: (description, setting_entry, type_hints[subsetting])
                        for subsetting, description in setting_entry.description.items()
                    })

        # Get the settings per filter as well.
        for filter_name, filter_type in self.loaded_filters.items():
            extra_fields_type = filter_type.extra_fields_type
            if not extra_fields_type:
                continue
            type_hints = get_type_hints(extra_fields_type)
            # A class var with a `_description` suffix is expected per field name.
            self.loaded_filter_settings[filter_name] = {
                field_name: (
                    getattr(extra_fields_type, f"{field_name}_description", ""),
                    extra_fields_type,
                    type_hints[field_name]
                )
                for field_name in extra_fields_type.__fields__
            }

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await has_any_role(*MODERATION_ROLES).predicate(ctx)

    # endregion
    # region: listeners

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Filter the contents of a sent message."""
        if msg.author.bot or msg.webhook_id or msg.type == MessageType.auto_moderation_action:
            return
        self.message_cache.append(msg)

        ctx = FilterContext(Event.MESSAGE, msg.author, msg.channel, msg.content, msg, msg.embeds)
        result_actions, list_messages, _ = await self._resolve_action(ctx)
        if result_actions:
            await result_actions.action(ctx)
        if ctx.send_alert:
            await self._send_alert(ctx, list_messages)

    # endregion
    # region: blacklist commands

    @commands.group(aliases=("bl", "blacklist", "denylist", "dl"))
    async def blocklist(self, ctx: Context) -> None:
        """Group for managing blacklisted items."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @blocklist.command(name="list", aliases=("get",))
    async def bl_list(self, ctx: Context, list_name: Optional[str] = None) -> None:
        """List the contents of a specified blacklist."""
        result = await self._resolve_list_type_and_name(ctx, ListType.DENY, list_name, exclude="list_type")
        if not result:
            return
        list_type, filter_list = result
        await self._send_list(ctx, filter_list, list_type)

    @blocklist.command(name="add", aliases=("a",))
    async def bl_add(
        self,
        ctx: Context,
        noui: Optional[Literal["noui"]],
        list_name: Optional[str],
        content: str,
        *,
        description_and_settings: Optional[str] = None
    ) -> None:
        """
        Add a blocked filter to the specified filter list.

        Unless `noui` is specified, a UI will be provided to edit the content, description, and settings
        before confirmation.

        The settings can be provided in the command itself, in the format of `setting_name=value` (no spaces around the
        equal sign). The value doesn't need to (shouldn't) be surrounded in quotes even if it contains spaces.
        """
        result = await self._resolve_list_type_and_name(ctx, ListType.DENY, list_name, exclude="list_type")
        if result is None:
            return
        list_type, filter_list = result
        await self._add_filter(ctx, noui, list_type, filter_list, content, description_and_settings)

    # endregion
    # region: whitelist commands

    @commands.group(aliases=("wl", "whitelist", "al"))
    async def allowlist(self, ctx: Context) -> None:
        """Group for managing blacklisted items."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @allowlist.command(name="list", aliases=("get",))
    async def al_list(self, ctx: Context, list_name: Optional[str] = None) -> None:
        """List the contents of a specified whitelist."""
        result = await self._resolve_list_type_and_name(ctx, ListType.ALLOW, list_name, exclude="list_type")
        if not result:
            return
        list_type, filter_list = result
        await self._send_list(ctx, filter_list, list_type)

    @allowlist.command(name="add", aliases=("a",))
    async def al_add(
        self,
        ctx: Context,
        noui: Optional[Literal["noui"]],
        list_name: Optional[str],
        content: str,
        *,
        description_and_settings: Optional[str] = None
    ) -> None:
        """
        Add an allowed filter to the specified filter list.

        Unless `noui` is specified, a UI will be provided to edit the content, description, and settings
        before confirmation.

        The settings can be provided in the command itself, in the format of `setting_name=value` (no spaces around the
        equal sign). The value doesn't need to (shouldn't) be surrounded in quotes even if it contains spaces.
        """
        result = await self._resolve_list_type_and_name(ctx, ListType.ALLOW, list_name, exclude="list_type")
        if result is None:
            return
        list_type, filter_list = result
        await self._add_filter(ctx, noui, list_type, filter_list, content, description_and_settings)

    # endregion
    # region: filter commands

    @commands.group(aliases=("filters", "f"), invoke_without_command=True)
    async def filter(self, ctx: Context, id_: Optional[int] = None) -> None:
        """
        Group for managing filters.

        If a valid filter ID is provided, an embed describing the filter will be posted.
        """
        if not ctx.invoked_subcommand and not id_:
            await ctx.send_help(ctx.command)
            return

        result = self._get_filter_by_id(id_)
        if result is None:
            await ctx.send(f":x: Could not find a filter with ID `{id_}`.")
            return
        filter_, filter_list, list_type = result

        overrides_values, extra_fields_overrides = filter_serializable_overrides(filter_)

        all_settings_repr_dict = build_filter_repr_dict(
            filter_list, list_type, type(filter_), overrides_values, extra_fields_overrides
        )
        embed = Embed(colour=Colour.blue())
        populate_embed_from_dict(embed, all_settings_repr_dict)
        embed.description = f"`{filter_.content}`"
        if filter_.description:
            embed.description += f" - {filter_.description}"
        embed.set_author(name=f"Filter #{id_} - " + f"{filter_list[list_type].label}".title())
        embed.set_footer(text=(
            "Field names with an asterisk have values which override the defaults of the containing filter list. "
            f"To view all defaults of the list, "
            f"run `{constants.Bot.prefix}filterlist describe {list_type.name} {filter_list.name}`."
        ))
        await ctx.send(embed=embed)

    @filter.command(name="list", aliases=("get",))
    async def f_list(
        self, ctx: Context, list_type: Optional[list_type_converter] = None, list_name: Optional[str] = None
    ) -> None:
        """List the contents of a specified list of filters."""
        result = await self._resolve_list_type_and_name(ctx, list_type, list_name)
        if result is None:
            return
        list_type, filter_list = result

        await self._send_list(ctx, filter_list, list_type)

    @filter.command(name="describe", aliases=("explain", "manual"))
    async def f_describe(self, ctx: Context, filter_name: Optional[str]) -> None:
        """Show a description of the specified filter, or a list of possible values if no name is specified."""
        if not filter_name:
            filter_names = [f"» {f}" for f in self.loaded_filters]
            embed = Embed(colour=Colour.blue())
            embed.set_author(name="List of filter names")
            await LinePaginator.paginate(filter_names, ctx, embed, max_lines=10, empty=False)
        else:
            filter_type = self.loaded_filters.get(filter_name)
            if not filter_type:
                filter_type = self.loaded_filters.get(filter_name[:-1])  # A plural form or a typo.
                if not filter_type:
                    await ctx.send(f":x: There's no filter type named {filter_name!r}.")
                    return
            # Use the class's docstring, and ignore single newlines.
            embed = Embed(description=re.sub(r"(?<!\n)\n(?!\n)", " ", filter_type.__doc__), colour=Colour.blue())
            embed.set_author(name=f"Description of the {filter_name} filter")
            await ctx.send(embed=embed)

    @filter.command(name="add", aliases=("a",))
    async def f_add(
        self,
        ctx: Context,
        noui: Optional[Literal["noui"]],
        list_type: Optional[list_type_converter],
        list_name: Optional[str],
        content: str,
        *,
        description_and_settings: Optional[str] = None
    ) -> None:
        """
        Add a filter to the specified filter list.

        Unless `noui` is specified, a UI will be provided to edit the content, description, and settings
        before confirmation.

        The settings can be provided in the command itself, in the format of `setting_name=value` (no spaces around the
        equal sign). The value doesn't need to (shouldn't) be surrounded in quotes even if it contains spaces.

        A template filter can be specified in the settings area to copy overrides from. The setting name is "--template"
        and the value is the filter ID. The template will be used before applying any other override.

        Example: `!filter add denied token "Scaleios is great" delete_messages=True send_alert=False --template=100`
        """
        result = await self._resolve_list_type_and_name(ctx, list_type, list_name)
        if result is None:
            return
        list_type, filter_list = result
        await self._add_filter(ctx, noui, list_type, filter_list, content, description_and_settings)

    @filter.command(name="edit", aliases=("e",))
    async def f_edit(
        self,
        ctx: Context,
        noui: Optional[Literal["noui"]],
        filter_id: int,
        *,
        description_and_settings: Optional[str] = None
    ) -> None:
        """
        Edit a filter specified by its ID.

        Unless `noui` is specified, a UI will be provided to edit the content, description, and settings
        before confirmation.

        The settings can be provided in the command itself, in the format of `setting_name=value` (no spaces around the
        equal sign). The value doesn't need to (shouldn't) be surrounded in quotes even if it contains spaces.

        A template filter can be specified in the settings area to copy overrides from. The setting name is "--template"
        and the value is the filter ID. The template will be used before applying any other override.

        To edit the filter's content, use the UI.
        """
        result = self._get_filter_by_id(filter_id)
        if result is None:
            await ctx.send(f":x: Could not find a filter with ID `{filter_id}`.")
            return
        filter_, filter_list, list_type = result
        filter_type = type(filter_)
        settings, filter_settings = filter_serializable_overrides(filter_)
        description, new_settings, new_filter_settings = description_and_settings_converter(
            filter_list,
            list_type, filter_type,
            self.loaded_settings,
            self.loaded_filter_settings,
            description_and_settings
        )

        content = filter_.content
        description = description or filter_.description
        settings.update(new_settings)
        filter_settings.update(new_filter_settings)
        patch_func = partial(self._patch_filter, filter_)

        if noui:
            try:
                await patch_func(
                    ctx.message, filter_list, list_type, filter_type, content, description, settings, filter_settings
                )
            except ResponseCodeError as e:
                await ctx.reply(embed=format_response_error(e))
            return

        embed = Embed(colour=Colour.blue())
        embed.description = f"`{filter_.content}`"
        if description:
            embed.description += f" - {description}"
        embed.set_author(
            name=f"Filter #{filter_id} - {filter_list[list_type].label}".title())
        embed.set_footer(text=(
            "Field names with an asterisk have values which override the defaults of the containing filter list. "
            f"To view all defaults of the list, "
            f"run `{constants.Bot.prefix}filterlist describe {list_type.name} {filter_list.name}`."
        ))

        view = filters_ui.FilterEditView(
            filter_list,
            list_type,
            filter_type,
            content,
            description,
            settings,
            filter_settings,
            self.loaded_settings,
            self.loaded_filter_settings,
            ctx.author,
            embed,
            patch_func
        )
        await ctx.send(embed=embed, reference=ctx.message, view=view)

    @filter.command(name="delete", aliases=("d", "remove"))
    async def f_delete(self, ctx: Context, filter_id: int) -> None:
        """Delete the filter specified by its ID."""
        async def delete_list() -> None:
            """The actual removal routine."""
            await bot.instance.api_client.delete(f'bot/filter/filters/{filter_id}')
            filter_list[list_type].filters.pop(filter_id)
            await ctx.reply(f"✅ Deleted filter: {filter_}")

        result = self._get_filter_by_id(filter_id)
        if result is None:
            await ctx.send(f":x: Could not find a filter with ID `{filter_id}`.")
            return
        filter_, filter_list, list_type = result
        await ctx.reply(
            f"Are you sure you want to delete filter {filter_}?",
            view=DeleteConfirmationView(ctx.author, delete_list)
        )

    @filter.command(aliases=("settings",))
    async def setting(self, ctx: Context, setting_name: str | None) -> None:
        """Show a description of the specified setting, or a list of possible settings if no name is specified."""
        if not setting_name:
            settings_list = [f"» {setting_name}" for setting_name in self.loaded_settings]
            for filter_name, filter_settings in self.loaded_filter_settings.items():
                settings_list.extend(f"» {filter_name}/{setting}" for setting in filter_settings)
            embed = Embed(colour=Colour.blue())
            embed.set_author(name="List of setting names")
            await LinePaginator.paginate(settings_list, ctx, embed, max_lines=10, empty=False)

        else:
            # The setting is either in a SettingsEntry subclass, or a pydantic model.
            setting_data = self.loaded_settings.get(setting_name)
            description = None
            if setting_data:
                description = setting_data[0]
            elif "/" in setting_name:  # It's a filter specific setting.
                filter_name, filter_setting_name = setting_name.split("/", maxsplit=1)
                if filter_name in self.loaded_filter_settings:
                    if filter_setting_name in self.loaded_filter_settings[filter_name]:
                        description = self.loaded_filter_settings[filter_name][filter_setting_name][0]
            if description is None:
                await ctx.send(f":x: There's no setting type named {setting_name!r}.")
                return
            embed = Embed(colour=Colour.blue(), description=description)
            embed.set_author(name=f"Description of the {setting_name} setting")
            await ctx.send(embed=embed)

    @filter.command(name="match")
    async def f_match(
        self, ctx: Context, no_user: bool | None, message: Message | None, *, string: str | None
    ) -> None:
        """
        Post any responses from the filter lists for the given message or string.

        If there's a `message`, the `string` will be ignored. Note that if a `message` is provided, it will go through
        all validations appropriate to where it was sent and who sent it. To check for matches regardless of the author
        (for example if the message was sent by another staff member or yourself) set `no_user` to '1' or 'True'.

        If a `string` is provided, it will be validated in the context of a user with no roles in python-general.
        """
        if not message and not string:
            raise BadArgument("Please provide input.")
        if message:
            user = None if no_user else message.author
            filter_ctx = FilterContext(
                Event.MESSAGE, user, message.channel, message.content, message, message.embeds
            )
        else:
            filter_ctx = FilterContext(
                Event.MESSAGE, None, ctx.guild.get_channel(Channels.python_general), string, None
            )

        _, _, triggers = await self._resolve_action(filter_ctx)
        lines = []
        for filter_list, list_triggers in triggers.items():
            for sublist_type, sublist_triggers in list_triggers.items():
                if sublist_triggers:
                    triggers_repr = map(str, sublist_triggers)
                    lines.extend([f"**{filter_list[sublist_type].label.title()}s**", *triggers_repr, "\n"])
        lines = lines[:-1]  # Remove last newline.

        embed = Embed(colour=Colour.blue(), title="Match results")
        await LinePaginator.paginate(lines, ctx, embed, max_lines=10, empty=False)

    @filter.command(name="search")
    async def f_search(
        self,
        ctx: Context,
        noui: Literal["noui"] | None,
        filter_type_name: str | None,
        *,
        settings: str = ""
    ) -> None:
        """
        Find filters with the provided settings. The format is identical to that of the add and edit commands.

        If a list type and/or a list name are provided, the search will be limited to those parameters. A list name must
        be provided in order to search by filter-specific settings.
        """
        filter_type = None
        if filter_type_name:
            filter_type_name = filter_type_name.lower()
            filter_type = self.loaded_filters.get(filter_type_name)
            if not filter_type:
                self.loaded_filters.get(filter_type_name[:-1])  # In case the user tried to specify the plural form.
        # If settings were provided with no filter_type, discord.py will capture the first word as the filter type.
        if filter_type is None and filter_type_name is not None:
            if settings:
                settings = f"{filter_type_name} {settings}"
            else:
                settings = filter_type_name
            filter_type_name = None

        settings, filter_settings, filter_type = search_criteria_converter(
            self.filter_lists,
            self.loaded_filters,
            self.loaded_settings,
            self.loaded_filter_settings,
            filter_type,
            settings
        )

        if noui:
            await self._search_filters(ctx.message, filter_type, settings, filter_settings)
            return

        embed = Embed(colour=Colour.blue())
        view = SearchEditView(
            filter_type,
            settings,
            filter_settings,
            self.filter_lists,
            self.loaded_filters,
            self.loaded_settings,
            self.loaded_filter_settings,
            ctx.author,
            embed,
            self._search_filters
        )
        await ctx.send(embed=embed, reference=ctx.message, view=view)

    # endregion
    # region: filterlist group

    @commands.group(aliases=("fl",))
    async def filterlist(self, ctx: Context) -> None:
        """Group for managing filter lists."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @filterlist.command(name="describe", aliases=("explain", "manual", "id"))
    async def fl_describe(
        self, ctx: Context, list_type: Optional[list_type_converter] = None, list_name: Optional[str] = None
    ) -> None:
        """Show a description of the specified filter list, or a list of possible values if no values are provided."""
        if not list_type and not list_name:
            list_names = [f"» {fl}" for fl in self.filter_lists]
            embed = Embed(colour=Colour.blue())
            embed.set_author(name="List of filter lists names")
            await LinePaginator.paginate(list_names, ctx, embed, max_lines=10, empty=False)
            return

        result = await self._resolve_list_type_and_name(ctx, list_type, list_name)
        if result is None:
            return
        list_type, filter_list = result

        setting_values = {}
        for settings_group in filter_list[list_type].defaults:
            for _, setting in settings_group.items():
                setting_values.update(to_serializable(setting.dict()))

        embed = Embed(colour=Colour.blue())
        populate_embed_from_dict(embed, setting_values)
        # Use the class's docstring, and ignore single newlines.
        embed.description = re.sub(r"(?<!\n)\n(?!\n)", " ", filter_list.__doc__)
        embed.set_author(
            name=f"Description of the {filter_list[list_type].label} filter list"
        )
        await ctx.send(embed=embed)

    @filterlist.command(name="add", aliases=("a",))
    @has_any_role(Roles.admins)
    async def fl_add(self, ctx: Context, list_type: list_type_converter, list_name: str) -> None:
        """Add a new filter list."""
        list_description = f"{past_tense(list_type.name.lower())} {list_name.lower()}"
        if list_name in self.filter_lists:
            filter_list = self.filter_lists[list_name]
            if list_type in filter_list:
                await ctx.reply(f":x: The {list_description} filter list already exists.")
                return

        embed = Embed(colour=Colour.blue())
        embed.set_author(name=f"New Filter List - {list_description.title()}")
        settings = {name: starting_value(value[2]) for name, value in self.loaded_settings.items()}

        view = FilterListAddView(
            list_name,
            list_type,
            settings,
            self.loaded_settings,
            ctx.author,
            embed,
            self._post_filter_list
        )
        await ctx.send(embed=embed, reference=ctx.message, view=view)

    @filterlist.command(name="edit", aliases=("e",))
    @has_any_role(Roles.admins)
    async def fl_edit(
        self,
        ctx: Context,
        noui: Optional[Literal["noui"]],
        list_type: Optional[list_type_converter] = None,
        list_name: Optional[str] = None,
        *,
        settings: str | None
    ) -> None:
        """
        Edit the filter list.

        Unless `noui` is specified, a UI will be provided to edit the settings before confirmation.

        The settings can be provided in the command itself, in the format of `setting_name=value` (no spaces around the
        equal sign). The value doesn't need to (shouldn't) be surrounded in quotes even if it contains spaces.
        """
        result = await self._resolve_list_type_and_name(ctx, list_type, list_name)
        if result is None:
            return
        list_type, filter_list = result
        settings = settings_converter(self.loaded_settings, settings)
        if noui:
            try:
                await self._patch_filter_list(ctx.message, filter_list, list_type, settings)
            except ResponseCodeError as e:
                await ctx.reply(embed=format_response_error(e))
            return

        embed = Embed(colour=Colour.blue())
        embed.set_author(name=f"{filter_list[list_type].label.title()} Filter List")
        embed.set_footer(text="Field names with a ~ have values which change the existing value in the filter list.")

        view = FilterListEditView(
            filter_list,
            list_type,
            settings,
            self.loaded_settings,
            ctx.author,
            embed,
            self._patch_filter_list
        )
        await ctx.send(embed=embed, reference=ctx.message, view=view)

    @filterlist.command(name="delete", aliases=("remove",))
    @has_any_role(Roles.admins)
    async def fl_delete(
        self, ctx: Context, list_type: Optional[list_type_converter] = None, list_name: Optional[str] = None
    ) -> None:
        """Remove the filter list and all of its filters from the database."""
        async def delete_list() -> None:
            """The actual removal routine."""
            list_data = await bot.instance.api_client.get(f"bot/filter/filter_lists/{list_id}")
            file = discord.File(BytesIO(json.dumps(list_data, indent=4).encode("utf-8")), f"{list_description}.json")
            message = await ctx.send("⏳ Annihilation in progress, please hold...", file=file)
            # Unload the filter list.
            filter_list.pop(list_type)
            if not filter_list:  # There's nothing left, remove from the cog.
                self.filter_lists.pop(filter_list.name)
                self.unsubscribe(filter_list)

            await bot.instance.api_client.delete(f"bot/filter/filter_lists/{list_id}")
            await message.edit(content=f"✅ The {list_description} list has been deleted.")

        result = await self._resolve_list_type_and_name(ctx, list_type, list_name)
        if result is None:
            return
        list_type, filter_list = result
        list_id = filter_list[list_type].id
        list_description = filter_list[list_type].label
        await ctx.reply(
            f"Are you sure you want to delete the {list_description} list?",
            view=DeleteConfirmationView(ctx.author, delete_list)
        )

    # endregion
    # region: helper functions

    def _load_raw_filter_list(self, list_data: dict) -> AtomicList | None:
        """Load the raw list data to the cog."""
        list_name = list_data["name"]
        if list_name not in self.filter_lists:
            if list_name not in filter_list_types:
                if list_name not in self.already_warned:
                    log.warning(
                        f"A filter list named {list_name} was loaded from the database, but no matching class."
                    )
                    self.already_warned.add(list_name)
                return None
            self.filter_lists[list_name] = filter_list_types[list_name](self)
        return self.filter_lists[list_name].add_list(list_data)

    async def _resolve_action(
        self, ctx: FilterContext
    ) -> tuple[Optional[ActionSettings], dict[FilterList, list[str]], dict[FilterList, dict[ListType, list[Filter]]]]:
        """
        Return the actions that should be taken for all filter lists in the given context.

        Additionally, a message is possibly provided from each filter list describing the triggers,
        which should be relayed to the moderators.
        """
        actions = []
        messages = {}
        triggers = {}
        for filter_list in self._subscriptions[ctx.event]:
            list_actions, list_message, triggers[filter_list] = await filter_list.actions_for(ctx)
            if list_actions:
                actions.append(list_actions)
            if list_message:
                messages[filter_list] = list_message

        result_actions = None
        if actions:
            result_actions = reduce(operator.or_, (action for action in actions))

        return result_actions, messages, triggers

    async def _send_alert(self, ctx: FilterContext, triggered_filters: dict[FilterList, list[str]]) -> None:
        """Build an alert message from the filter context, and send it via the alert webhook."""
        if not self.webhook:
            return

        name = f"{ctx.event.name.replace('_', ' ').title()} Filter"
        embed = await build_mod_alert(ctx, triggered_filters)
        # There shouldn't be more than 10, but if there are it's not very useful to send them all.
        await self.webhook.send(username=name, content=ctx.alert_content, embeds=[embed, *ctx.alert_embeds][:10])

    async def _resolve_list_type_and_name(
        self, ctx: Context, list_type: ListType | None = None, list_name: str | None = None, *, exclude: str = ""
    ) -> tuple[ListType, FilterList] | None:
        """Prompt the user to complete the list type or list name if one of them is missing."""
        if list_name is None:
            args = [list_type] if exclude != "list_type" else []
            await ctx.send(
                "The **list_name** argument is unspecified. Please pick a value from the options below:",
                view=ArgumentCompletionView(ctx, args, "list_name", list(self.filter_lists), 1, None)
            )
            return None

        filter_list = self._get_list_by_name(list_name)
        if list_type is None:
            if len(filter_list) > 1:
                args = [list_name] if exclude != "list_name" else []
                await ctx.send(
                    "The **list_type** argument is unspecified. Please pick a value from the options below:",
                    view=ArgumentCompletionView(
                        ctx, args, "list_type", [option.name for option in ListType], 0, list_type_converter
                    )
                )
                return None
            list_type = list(filter_list)[0]
        return list_type, filter_list

    def _get_list_by_name(self, list_name: str) -> FilterList:
        """Get a filter list by its name, or raise an error if there's no such list."""
        log.trace(f"Getting the filter list matching the name {list_name}")
        filter_list = self.filter_lists.get(list_name)
        if not filter_list:
            if list_name.endswith("s"):  # The user may have attempted to use the plural form.
                filter_list = self.filter_lists.get(list_name[:-1])
            if not filter_list:
                raise BadArgument(f"There's no filter list named {list_name!r}.")
        log.trace(f"Found list named {filter_list.name}")
        return filter_list

    @staticmethod
    async def _send_list(ctx: Context, filter_list: FilterList, list_type: ListType) -> None:
        """Show the list of filters identified by the list name and type."""
        if list_type not in filter_list:
            await ctx.send(f":x: There is no list of {past_tense(list_type.name.lower())} {filter_list.name}s.")
            return

        lines = list(map(str, filter_list[list_type].filters.values()))
        log.trace(f"Sending a list of {len(lines)} filters.")

        embed = Embed(colour=Colour.blue())
        embed.set_author(name=f"List of {filter_list[list_type].label}s ({len(lines)} total)")

        await LinePaginator.paginate(lines, ctx, embed, max_lines=15, empty=False, reply=True)

    def _get_filter_by_id(self, id_: int) -> Optional[tuple[Filter, FilterList, ListType]]:
        """Get the filter object corresponding to the provided ID, along with its containing list and list type."""
        for filter_list in self.filter_lists.values():
            for list_type, sublist in filter_list.items():
                if id_ in sublist.filters:
                    return sublist.filters[id_], filter_list, list_type

    async def _add_filter(
        self,
        ctx: Context,
        noui: Optional[Literal["noui"]],
        list_type: ListType,
        filter_list: FilterList,
        content: str,
        description_and_settings: Optional[str] = None
    ) -> None:
        """Add a filter to the database."""
        filter_type = filter_list.get_filter_type(content)
        description, settings, filter_settings = description_and_settings_converter(
            filter_list,
            list_type,
            filter_type,
            self.loaded_settings,
            self.loaded_filter_settings,
            description_and_settings
        )

        if noui:
            try:
                await self._post_new_filter(
                    ctx.message, filter_list, list_type, filter_type, content, description, settings, filter_settings
                )
            except ResponseCodeError as e:
                await ctx.reply(embed=format_response_error(e))
            except ValueError as e:
                raise BadArgument(str(e))
            return

        embed = Embed(colour=Colour.blue())
        embed.description = f"`{content}`" if content else "*No content*"
        if description:
            embed.description += f" - {description}"
        embed.set_author(
            name=f"New Filter - {filter_list[list_type].label}".title())
        embed.set_footer(text=(
            "Field names with an asterisk have values which override the defaults of the containing filter list. "
            f"To view all defaults of the list, "
            f"run `{constants.Bot.prefix}filterlist describe {list_type.name} {filter_list.name}`."
        ))

        view = filters_ui.FilterEditView(
            filter_list,
            list_type,
            filter_type,
            content,
            description,
            settings,
            filter_settings,
            self.loaded_settings,
            self.loaded_filter_settings,
            ctx.author,
            embed,
            self._post_new_filter
        )
        await ctx.send(embed=embed, reference=ctx.message, view=view)

    @staticmethod
    def _identical_filters_message(content: str, filter_list: FilterList, list_type: ListType, filter_: Filter) -> str:
        """Returns all the filters in the list with content identical to the content supplied."""
        if list_type not in filter_list:
            return ""
        duplicates = [
            f for f in filter_list[list_type].filters.values()
            if f.content == content and f.id != filter_.id
        ]
        msg = ""
        if duplicates:
            msg = f"\n:warning: The filter(s) #{', #'.join(str(dup.id) for dup in duplicates)} have the same content. "
            msg += "Please make sure this is intentional."

        return msg

    @staticmethod
    async def _post_new_filter(
        msg: Message,
        filter_list: FilterList,
        list_type: ListType,
        filter_type: type[Filter],
        content: str,
        description: str | None,
        settings: dict,
        filter_settings: dict
    ) -> None:
        """POST the data of the new filter to the site API."""
        valid, error_msg = filter_type.validate_filter_settings(filter_settings)
        if not valid:
            raise BadArgument(f"Error while validating filter-specific settings: {error_msg}")

        content = await filter_type.process_content(content)

        list_id = filter_list[list_type].id
        description = description or None
        payload = {
            "filter_list": list_id, "content": content, "description": description,
            "additional_field": json.dumps(filter_settings), **settings
        }
        response = await bot.instance.api_client.post('bot/filter/filters', json=to_serializable(payload))
        new_filter = filter_list.add_filter(list_type, response)
        if new_filter:
            extra_msg = Filtering._identical_filters_message(content, filter_list, list_type, new_filter)
            await msg.reply(f"✅ Added filter: {new_filter}" + extra_msg)
        else:
            await msg.reply(":x: Could not create the filter. Are you sure it's implemented?")

    @staticmethod
    async def _patch_filter(
        filter_: Filter,
        msg: Message,
        filter_list: FilterList,
        list_type: ListType,
        filter_type: type[Filter],
        content: str,
        description: str | None,
        settings: dict,
        filter_settings: dict
    ) -> None:
        """PATCH the new data of the filter to the site API."""
        valid, error_msg = filter_type.validate_filter_settings(filter_settings)
        if not valid:
            raise BadArgument(f"Error while validating filter-specific settings: {error_msg}")

        if content != filter_.content:
            content = await filter_type.process_content(content)

        # If the setting is not in `settings`, the override was either removed, or there wasn't one in the first place.
        for current_settings in (filter_.actions, filter_.validations):
            if current_settings:
                for setting_entry in current_settings.values():
                    settings.update({setting: None for setting in setting_entry.dict() if setting not in settings})

        description = description or None
        payload = {
            "content": content, "description": description, "additional_field": json.dumps(filter_settings), **settings
        }
        response = await bot.instance.api_client.patch(
            f'bot/filter/filters/{filter_.id}', json=to_serializable(payload)
        )
        # Return type can be None, but if it's being edited then it's not supposed to be.
        edited_filter = filter_list.add_filter(list_type, response)
        extra_msg = Filtering._identical_filters_message(content, filter_list, list_type, edited_filter)
        await msg.reply(f"✅ Edited filter: {edited_filter}" + extra_msg)

    async def _post_filter_list(self, msg: Message, list_name: str, list_type: ListType, settings: dict) -> None:
        """POST the new data of the filter list to the site API."""
        payload = {"name": list_name, "list_type": list_type.value, **to_serializable(settings)}
        response = await bot.instance.api_client.post('bot/filter/filter_lists', json=payload)
        self._load_raw_filter_list(response)
        await msg.reply(f"✅ Added a new filter list: {past_tense(list_type.name.lower())} {list_name}")

    @staticmethod
    async def _patch_filter_list(msg: Message, filter_list: FilterList, list_type: ListType, settings: dict) -> None:
        """PATCH the new data of the filter list to the site API."""
        list_id = filter_list[list_type].id
        response = await bot.instance.api_client.patch(
            f'bot/filter/filter_lists/{list_id}', json=to_serializable(settings)
        )
        filter_list.pop(list_type, None)
        filter_list.add_list(response)
        await msg.reply(f"✅ Edited filter list: {filter_list[list_type].label}")

    def _filter_match_query(
        self, filter_: Filter, settings_query: dict, filter_settings_query: dict, differ_by_default: set[str]
    ) -> bool:
        """Return whether the given filter matches the query."""
        override_matches = set()
        overrides, _ = filter_.overrides
        for setting_name, setting_value in settings_query.items():
            if setting_name not in overrides:
                continue
            if repr_equals(overrides[setting_name], setting_value):
                override_matches.add(setting_name)
            else:  # If an override doesn't match then the filter doesn't match.
                return False
        if not (differ_by_default <= override_matches):  # The overrides didn't cover for the default mismatches.
            return False

        filter_settings = filter_.extra_fields.dict() if filter_.extra_fields else {}
        # If the dict changes then some fields were not the same.
        return (filter_settings | filter_settings_query) == filter_settings

    def _search_filter_list(
        self, atomic_list: AtomicList, filter_type: type[Filter] | None, settings: dict, filter_settings: dict
    ) -> list[Filter]:
        """Find all filters in the filter list which match the settings."""
        # If the default answers are known, only the overrides need to be checked for each filter.
        all_defaults = atomic_list.defaults.dict()
        match_by_default = set()
        differ_by_default = set()
        for setting_name, setting_value in settings.items():
            if repr_equals(all_defaults[setting_name], setting_value):
                match_by_default.add(setting_name)
            else:
                differ_by_default.add(setting_name)

        result_filters = []
        for filter_ in atomic_list.filters.values():
            if filter_type and not isinstance(filter_, filter_type):
                continue
            if self._filter_match_query(filter_, settings, filter_settings, differ_by_default):
                result_filters.append(filter_)

        return result_filters

    async def _search_filters(
        self, message: Message, filter_type: type[Filter] | None, settings: dict, filter_settings: dict
    ) -> None:
        """Find all filters which match the settings and display them."""
        lines = []
        result_count = 0
        for filter_list in self.filter_lists.values():
            if filter_type and filter_type not in filter_list.filter_types:
                continue
            for atomic_list in filter_list.values():
                list_results = self._search_filter_list(atomic_list, filter_type, settings, filter_settings)
                if list_results:
                    lines.append(f"**{atomic_list.label.title()}**")
                    lines.extend(map(str, list_results))
                    lines.append("")
                    result_count += len(list_results)

        embed = Embed(colour=Colour.blue())
        embed.set_author(name=f"Search Results ({result_count} total)")
        ctx = await bot.instance.get_context(message)
        await LinePaginator.paginate(lines, ctx, embed, max_lines=15, empty=False, reply=True)

    # endregion


async def setup(bot: Bot) -> None:
    """Load the Filtering cog."""
    await bot.add_cog(Filtering(bot))
