import json
import operator
import re
from collections import defaultdict
from functools import partial, reduce
from typing import Literal, Optional, get_type_hints

from discord import Colour, Embed, HTTPException, Message
from discord.ext import commands
from discord.ext.commands import BadArgument, Cog, Context, has_any_role
from discord.utils import escape_markdown

import bot
import bot.exts.filtering._ui as filters_ui
from bot.bot import Bot
from bot.constants import Colours, MODERATION_ROLES, Webhooks
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists import FilterList, ListType, filter_list_types, list_type_converter
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._settings import ActionSettings
from bot.exts.filtering._ui import (
    ArgumentCompletionView, build_filter_repr_dict, description_and_settings_converter, populate_embed_from_dict
)
from bot.exts.filtering._utils import past_tense, to_serializable
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils.messages import format_channel, format_user

log = get_logger(__name__)


class Filtering(Cog):
    """Filtering and alerting for content posted on the server."""

    # region: init

    def __init__(self, bot: Bot):
        self.bot = bot
        self.filter_lists: dict[str, FilterList] = {}
        self._subscriptions: defaultdict[Event, list[FilterList]] = defaultdict(list)
        self.webhook = None

        self.loaded_settings = {}
        self.loaded_filters = {}
        self.loaded_filter_settings = {}

    async def cog_load(self) -> None:
        """
        Fetch the filter data from the API, parse it, and load it to the appropriate data structures.

        Additionally, fetch the alerting webhook.
        """
        await self.bot.wait_until_guild_available()
        already_warned = set()

        raw_filter_lists = await self.bot.api_client.get("bot/filter/filter_lists")
        for raw_filter_list in raw_filter_lists:
            list_name = raw_filter_list["name"]
            if list_name not in self.filter_lists:
                if list_name not in filter_list_types:
                    if list_name not in already_warned:
                        log.warning(
                            f"A filter list named {list_name} was loaded from the database, but no matching class."
                        )
                        already_warned.add(list_name)
                    continue
                self.filter_lists[list_name] = filter_list_types[list_name](self)
            self.filter_lists[list_name].add_list(raw_filter_list)

        try:
            self.webhook = await self.bot.fetch_webhook(Webhooks.filters)
        except HTTPException:
            log.error(f"Failed to fetch filters webhook with ID `{Webhooks.filters}`.")

        self.collect_loaded_types()

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

    def collect_loaded_types(self) -> None:
        """
        Go over the classes used in initialization and collect them to dictionaries.

        The information that is collected is about the types actually used to load the API response, not all types
        available in the filtering extension.
        """
        # Get the filter types used by each filter list.
        for filter_list in self.filter_lists.values():
            self.loaded_filters.update({filter_type.name: filter_type for filter_type in filter_list.filter_types})

        # Get the setting types used by each filter list.
        if self.filter_lists:
            # Any filter list has the fields for all settings in the DB schema, so picking any one of them is enough.
            list_defaults = list(list(self.filter_lists.values())[0].defaults.values())[0]
            settings_types = set()
            # The settings are split between actions and validations.
            settings_types.update(type(setting) for _, setting in list_defaults["actions"].items())
            settings_types.update(type(setting) for _, setting in list_defaults["validations"].items())
            for setting_type in settings_types:
                type_hints = get_type_hints(setting_type)
                # The description should be either a string or a dictionary.
                if isinstance(setting_type.description, str):
                    # If it's a string, then the setting matches a single field in the DB,
                    # and its name is the setting type's name attribute.
                    self.loaded_settings[setting_type.name] = (
                        setting_type.description, setting_type, type_hints[setting_type.name]
                    )
                else:
                    # Otherwise, the setting type works with compound settings.
                    self.loaded_settings.update({
                        subsetting: (description, setting_type, type_hints[subsetting])
                        for subsetting, description in setting_type.description.items()
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
        if msg.author.bot or msg.webhook_id:
            return

        ctx = FilterContext(Event.MESSAGE, msg.author, msg.channel, msg.content, msg, msg.embeds)

        result_actions, list_messages = await self._resolve_action(ctx)
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
        result = self._resolve_list_type_and_name(ctx, ListType.DENY, list_name)
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
        result = await self._resolve_list_type_and_name(ctx, ListType.DENY, list_name)
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
        result = self._resolve_list_type_and_name(ctx, ListType.ALLOW, list_name)
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
        result = await self._resolve_list_type_and_name(ctx, ListType.ALLOW, list_name)
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

        overrides_values, extra_fields_overrides = self._filter_overrides(filter_)

        all_settings_repr_dict = build_filter_repr_dict(
            filter_list, list_type, type(filter_), overrides_values, extra_fields_overrides
        )
        embed = Embed(colour=Colour.blue())
        populate_embed_from_dict(embed, all_settings_repr_dict)
        embed.description = f"`{filter_.content}`"
        if filter_.description:
            embed.description += f" - {filter_.description}"
        embed.set_author(name=f"Filter #{id_} - " + f"{past_tense(list_type.name.lower())} {filter_list.name}".title())
        embed.set_footer(text=(
            "Field names with an asterisk have values which override the defaults of the containing filter list. "
            f"To view all defaults of the list, run `!filterlist describe {list_type.name} {filter_list.name}`."
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
            embed = Embed(description="\n".join(self.loaded_filters))
            embed.set_author(name="List of filter names")
        else:
            filter_type = self.loaded_filters.get(filter_name)
            if not filter_type:
                filter_type = self.loaded_filters.get(filter_name[:-1])  # A plural form or a typo.
                if not filter_type:
                    await ctx.send(f":x: There's no filter type named {filter_name!r}.")
                    return
            # Use the class's docstring, and ignore single newlines.
            embed = Embed(description=re.sub(r"(?<!\n)\n(?!\n)", " ", filter_type.__doc__))
            embed.set_author(name=f"Description of the {filter_name} filter")
        embed.colour = Colour.blue()
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

        Example: `!filter add denied token "Scaleios is great" delete_messages=True send_alert=False`
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

        To edit the filter's content, use the UI.
        """
        result = self._get_filter_by_id(filter_id)
        if result is None:
            await ctx.send(f":x: Could not find a filter with ID `{filter_id}`.")
            return
        filter_, filter_list, list_type = result
        filter_type = type(filter_)
        settings, filter_settings = self._filter_overrides(filter_)
        description, new_settings, new_filter_settings = description_and_settings_converter(
            filter_list.name, self.loaded_settings, self.loaded_filter_settings, description_and_settings
        )

        content = filter_.content
        description = description or filter_.description
        settings.update(new_settings)
        filter_settings.update(new_filter_settings)
        patch_func = partial(self._patch_filter, filter_)

        if noui:
            await patch_func(
                ctx.message, filter_list, list_type, filter_type, content, description, settings, filter_settings
            )

        else:
            embed = Embed(colour=Colour.blue())
            embed.description = f"`{filter_.content}`"
            if description:
                embed.description += f" - {description}"
            embed.set_author(
                name=f"Filter #{filter_id} - {past_tense(list_type.name.lower())} {filter_list.name}".title())
            embed.set_footer(text=(
                "Field names with an asterisk have values which override the defaults of the containing filter list. "
                f"To view all defaults of the list, run `!filterlist describe {list_type.name} {filter_list.name}`."
            ))

            view = filters_ui.SettingsEditView(
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
        result = self._get_filter_by_id(filter_id)
        if result is None:
            await ctx.send(f":x: Could not find a filter with ID `{filter_id}`.")
            return
        filter_, filter_list, list_type = result
        await bot.instance.api_client.delete(f'bot/filter/filters/{filter_id}')
        filter_list.filter_lists[list_type].pop(filter_id)
        await ctx.reply(f"✅ Deleted filter: {filter_}")

    @filter.group(aliases=("settings",))
    async def setting(self, ctx: Context) -> None:
        """Group for settings-related commands."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @setting.command(name="describe", aliases=("explain", "manual"))
    async def s_describe(self, ctx: Context, setting_name: Optional[str]) -> None:
        """Show a description of the specified setting, or a list of possible settings if no name is specified."""
        if not setting_name:
            settings_list = list(self.loaded_settings)
            for filter_name, filter_settings in self.loaded_filter_settings.items():
                settings_list.extend(f"{filter_name}/{setting}" for setting in filter_settings)
            embed = Embed(description="\n".join(settings_list))
            embed.set_author(name="List of setting names")
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
            embed = Embed(description=description)
            embed.set_author(name=f"Description of the {setting_name} setting")
        embed.colour = Colour.blue()
        await ctx.send(embed=embed)

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
            embed = Embed(description="\n".join(f"\u2003 {fl}" for fl in self.filter_lists), colour=Colour.blue())
            embed.set_author(name="List of filter lists names")
            await ctx.send(embed=embed)
            return

        result = await self._resolve_list_type_and_name(ctx, list_type, list_name)
        if result is None:
            return
        list_type, filter_list = result

        list_defaults = filter_list.defaults[list_type]
        setting_values = {}
        for type_ in ("actions", "validations"):
            for _, setting in list_defaults[type_].items():
                setting_values.update(to_serializable(setting.dict()))

        embed = Embed(colour=Colour.blue())
        populate_embed_from_dict(embed, setting_values)
        # Use the class's docstring, and ignore single newlines.
        embed.description = re.sub(r"(?<!\n)\n(?!\n)", " ", filter_list.__doc__)
        embed.set_author(
            name=f"Description of the {past_tense(list_type.name.lower())} {list_name.title()} filter list"
        )
        await ctx.send(embed=embed)

    # endregion
    # region: helper functions

    async def _resolve_action(self, ctx: FilterContext) -> tuple[Optional[ActionSettings], dict[FilterList, str]]:
        """
        Return the actions that should be taken for all filter lists in the given context.

        Additionally, a message is possibly provided from each filter list describing the triggers,
        which should be relayed to the moderators.
        """
        actions = []
        messages = {}
        for filter_list in self._subscriptions[ctx.event]:
            list_actions, list_message = await filter_list.actions_for(ctx)
            if list_actions:
                actions.append(list_actions)
            if list_message:
                messages[filter_list] = list_message

        result_actions = None
        if actions:
            result_actions = reduce(operator.or_, (action for action in actions))

        return result_actions, messages

    async def _send_alert(self, ctx: FilterContext, triggered_filters: dict[FilterList, str]) -> None:
        """Build an alert message from the filter context, and send it via the alert webhook."""
        if not self.webhook:
            return

        name = f"{ctx.event.name.replace('_', ' ').title()} Filter"

        embed = Embed(color=Colours.soft_orange)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        triggered_by = f"**Triggered by:** {format_user(ctx.author)}"
        if ctx.channel.guild:
            triggered_in = f"**Triggered in:** {format_channel(ctx.channel)}"
        else:
            triggered_in = "**Triggered in:** :warning:**DM**:warning:"

        filters = []
        for filter_list, list_message in triggered_filters.items():
            if list_message:
                filters.append(f"**{filter_list.name.title()} Filters:** {list_message}")
        filters = "\n".join(filters)

        matches = "**Matches:** " + ", ".join(repr(match) for match in ctx.matches)
        actions = "**Actions Taken:** " + (", ".join(ctx.action_descriptions) if ctx.action_descriptions else "-")
        content = f"**[Original Content]({ctx.message.jump_url})**: {escape_markdown(ctx.content)}"

        embed_content = "\n".join(
            part for part in (triggered_by, triggered_in, filters, matches, actions, content) if part
        )
        if len(embed_content) > 4000:
            embed_content = embed_content[:4000] + " [...]"
        embed.description = embed_content

        await self.webhook.send(username=name, content=ctx.alert_content, embeds=[embed, *ctx.alert_embeds][:10])

    async def _resolve_list_type_and_name(
        self, ctx: Context, list_type: Optional[ListType] = None, list_name: Optional[str] = None
    ) -> Optional[tuple[ListType, FilterList]]:
        """Prompt the user to complete the list type or list name if one of them is missing."""
        if list_name is None:
            await ctx.send(
                "The **list_name** argument is unspecified. Please pick a value from the options below:",
                view=ArgumentCompletionView(ctx, [list_type], "list_name", list(self.filter_lists), 1, None)
            )
            return None

        filter_list = self._get_list_by_name(list_name)
        if list_type is None:
            if len(filter_list.filter_lists) > 1:
                await ctx.send(
                    "The **list_type** argument is unspecified. Please pick a value from the options below:",
                    view=ArgumentCompletionView(
                        ctx, [list_name], "list_type", [option.name for option in ListType], 0, list_type_converter
                    )
                )
                return None
            list_type = list(filter_list.filter_lists)[0]
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
        type_filters = filter_list.filter_lists.get(list_type)
        if type_filters is None:
            await ctx.send(f":x: There is no list of {past_tense(list_type.name.lower())} {filter_list.name}s.")
            return

        lines = list(map(str, type_filters.values()))
        log.trace(f"Sending a list of {len(lines)} filters.")

        embed = Embed(colour=Colour.blue())
        embed.set_author(name=f"List of {past_tense(list_type.name.lower())} {filter_list.name}s ({len(lines)} total)")

        await LinePaginator.paginate(lines, ctx, embed, max_lines=15, empty=False)

    def _get_filter_by_id(self, id_: int) -> Optional[tuple[Filter, FilterList, ListType]]:
        """Get the filter object corresponding to the provided ID, along with its containing list and list type."""
        for filter_list in self.filter_lists.values():
            for list_type, sublist in filter_list.filter_lists.items():
                if id_ in sublist:
                    return sublist[id_], filter_list, list_type

    @staticmethod
    def _filter_overrides(filter_: Filter) -> tuple[dict, dict]:
        """Get the filter's overrides to the filter list settings and the extra fields settings."""
        overrides_values = {}
        for settings in (filter_.actions, filter_.validations):
            if settings:
                for _, setting in settings.items():
                    overrides_values.update(to_serializable(setting.dict()))

        if filter_.extra_fields_type:
            extra_fields_overrides = filter_.extra_fields.dict(exclude_unset=True)
        else:
            extra_fields_overrides = {}

        return overrides_values, extra_fields_overrides

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
        description, settings, filter_settings = description_and_settings_converter(
            filter_list.name, self.loaded_settings, self.loaded_filter_settings, description_and_settings
        )
        filter_type = filter_list.get_filter_type(content)

        if noui:
            await self._post_new_filter(
                ctx.message, filter_list, list_type, filter_type, content, description, settings, filter_settings
            )

        else:
            embed = Embed(colour=Colour.blue())
            embed.description = f"`{content}`" if content else "*No content*"
            if description:
                embed.description += f" - {description}"
            embed.set_author(
                name=f"New Filter - {past_tense(list_type.name.lower())} {filter_list.name}".title())
            embed.set_footer(text=(
                "Field names with an asterisk have values which override the defaults of the containing filter list. "
                f"To view all defaults of the list, run `!filterlist describe {list_type.name} {filter_list.name}`."
            ))

            view = filters_ui.SettingsEditView(
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

        list_id = filter_list.list_ids[list_type]
        description = description or None
        payload = {
            "filter_list": list_id, "content": content, "description": description,
            "additional_field": json.dumps(filter_settings), **settings
        }
        response = await bot.instance.api_client.post('bot/filter/filters', json=payload)
        new_filter = filter_list.add_filter(response, list_type)
        await msg.reply(f"✅ Added filter: {new_filter}")

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

        # If the setting is not in `settings`, the override was either removed, or there wasn't one in the first place.
        for current_settings in (filter_.actions, filter_.validations):
            if current_settings:
                for _, setting_entry in current_settings.items():
                    settings.update({setting: None for setting in setting_entry.dict() if setting not in settings})

        list_id = filter_list.list_ids[list_type]
        description = description or None
        payload = {
            "filter_list": list_id, "content": content, "description": description,
            "additional_field": json.dumps(filter_settings), **settings
        }
        response = await bot.instance.api_client.patch(f'bot/filter/filters/{filter_.id}', json=payload)
        edited_filter = filter_list.add_filter(response, list_type)
        await msg.reply(f"✅ Edited filter: {edited_filter}")

    # endregion


async def setup(bot: Bot) -> None:
    """Load the Filtering cog."""
    await bot.add_cog(Filtering(bot))
