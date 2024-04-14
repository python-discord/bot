from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from enum import EnumMeta
from functools import partial
from typing import Any, TypeVar, get_origin

import discord
from discord import Embed, Interaction, Member, User
from discord.ext.commands import BadArgument, Context, Converter
from discord.ui.select import MISSING as SELECT_MISSING, SelectOption
from discord.utils import escape_markdown
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils import scheduling
from pydis_core.utils.logging import get_logger
from pydis_core.utils.members import get_or_fetch_member
from pydis_core.utils.regex import DISCORD_INVITE

import bot
from bot.constants import Colours
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists import FilterList
from bot.exts.filtering._utils import FakeContext, normalize_type
from bot.utils.lock import lock_arg
from bot.utils.messages import format_channel, format_user, upload_log

log = get_logger(__name__)


# Max number of characters in a Discord embed field value, minus 6 characters for a placeholder.
MAX_FIELD_SIZE = 1018
# Max number of characters for an embed field's value before it should take its own line.
MAX_INLINE_SIZE = 50
# Number of seconds before a settings editing view timeout.
EDIT_TIMEOUT = 600
# Number of seconds before timeout of an editing component.
COMPONENT_TIMEOUT = 180
# Amount of seconds to confirm the operation.
DELETION_TIMEOUT = 60
# Max length of modal title
MAX_MODAL_TITLE_LENGTH = 45
# Max number of items in a select
MAX_SELECT_ITEMS = 25
MAX_EMBED_DESCRIPTION = 4080
# Number of seconds before timeout of the alert view
ALERT_VIEW_TIMEOUT = 3600

SETTINGS_DELIMITER = re.compile(r"\s+(?=\S+=\S+)")
SINGLE_SETTING_PATTERN = re.compile(r"(--)?[\w/]+=.+")

EDIT_CONFIRMED_MESSAGE = "✅ Edit for `{0}` confirmed"

# Sentinel value to denote that a value is missing
MISSING = object()

T = TypeVar("T")


async def _build_alert_message_content(ctx: FilterContext, current_message_length: int) -> str:
    """Build the content section of the alert."""
    # For multiple messages and those with attachments or excessive newlines, use the logs API
    if ctx.messages_deletion and ctx.upload_deletion_logs and any((
        ctx.related_messages,
        len(ctx.uploaded_attachments) > 0,
        ctx.content.count("\n") > 15
    )):
        to_upload = {ctx.message} | ctx.related_messages if ctx.message else ctx.related_messages
        url = await upload_log(to_upload, bot.instance.user.id, ctx.uploaded_attachments)
        return f"A complete log of the offending messages can be found [here]({url})"

    alert_content = escape_markdown(ctx.content)
    remaining_chars = MAX_EMBED_DESCRIPTION - current_message_length

    if len(alert_content) > remaining_chars:
        if ctx.messages_deletion and ctx.upload_deletion_logs:
            url = await upload_log([ctx.message], bot.instance.user.id, ctx.uploaded_attachments)
            log_site_msg = f"The full message can be found [here]({url})"
            # 7 because that's the length of "[...]\n\n"
            return alert_content[:remaining_chars - (7 + len(log_site_msg))] + "[...]\n\n" + log_site_msg
        return alert_content[:remaining_chars - 5] + "[...]"

    return alert_content


async def build_mod_alert(ctx: FilterContext, triggered_filters: dict[FilterList, list[str]]) -> Embed:
    """Build an alert message from the filter context."""
    embed = Embed(color=Colours.soft_orange)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    triggered_by = f"**Triggered by:** {format_user(ctx.author)}"
    if ctx.channel:
        if ctx.channel.guild:
            triggered_in = f"**Triggered in:** {format_channel(ctx.channel)}\n"
        else:
            triggered_in = "**Triggered in:** :warning:**DM**:warning:\n"
        if len(ctx.related_channels) > 1:
            triggered_in += f"**Channels:** {', '.join(channel.mention for channel in ctx.related_channels)}\n"
    else:
        triggered_by += "\n"
        triggered_in = ""

    filters = []
    for filter_list, list_message in triggered_filters.items():
        if list_message:
            filters.append(f"**{filter_list.name.title()} Filters:** {', '.join(list_message)}")
    filters = "\n".join(filters)

    matches = "**Matches:** " + escape_markdown(", ".join(repr(match) for match in ctx.matches)) if ctx.matches else ""
    actions = "\n**Actions Taken:** " + (", ".join(ctx.action_descriptions) if ctx.action_descriptions else "-")

    mod_alert_message = "\n".join(part for part in (triggered_by, triggered_in, filters, matches, actions) if part)
    log.debug(f"{ctx.event.name} Filter:\n{mod_alert_message}")

    if ctx.message:
        mod_alert_message += f"\n**[Original Content]({ctx.message.jump_url})**:\n"
    else:
        mod_alert_message += "\n**Original Content**:\n"
    mod_alert_message += await _build_alert_message_content(ctx, len(mod_alert_message))

    embed.description = mod_alert_message
    return embed


def populate_embed_from_dict(embed: Embed, data: dict) -> None:
    """Populate a Discord embed by populating fields from the given dict."""
    for setting, value in data.items():
        if setting.startswith("_"):
            continue
        if isinstance(value, list | set | tuple):
            value = f"[{', '.join(map(str, value))}]"
        else:
            value = str(value) if value not in ("", None) else "-"
        if len(value) > MAX_FIELD_SIZE:
            value = value[:MAX_FIELD_SIZE] + " [...]"
        embed.add_field(name=setting, value=value, inline=len(value) < MAX_INLINE_SIZE)


def parse_value(value: str, type_: type[T]) -> T:
    """Parse the value provided in the CLI and attempt to convert it to the provided type."""
    blank = value == '""'
    type_ = normalize_type(type_, prioritize_nonetype=blank)

    if blank or isinstance(None, type_):
        return type_()
    if type_ in (tuple, list, set):
        return list(value.split(","))
    if type_ is bool:
        return value.lower() == "true" or value == "1"
    if isinstance(type_, EnumMeta):
        return type_[value.upper()]

    return type_(value)


def format_response_error(e: ResponseCodeError) -> Embed:
    """Format the response error into an embed."""
    description = ""
    if isinstance(e.response_json, list):
        description = "\n".join(f"- {error}" for error in e.response_json)
    elif isinstance(e.response_json, dict):
        if "non_field_errors" in e.response_json:
            non_field_errors = e.response_json.pop("non_field_errors")
            description += "\n".join(f"- {error}" for error in non_field_errors) + "\n"
        for field, errors in e.response_json.items():
            description += "\n".join(f"- {field} - {error}" for error in errors) + "\n"

    description = description.strip()
    if len(description) > MAX_EMBED_DESCRIPTION:
        description = description[:MAX_EMBED_DESCRIPTION] + "[...]"
    if not description:
        description = "Something unexpected happened, check the logs."

    embed = Embed(colour=discord.Colour.red(), title="Oops...", description=description)
    return embed


class ArgumentCompletionSelect(discord.ui.Select):
    """A select detailing the options that can be picked to assign to a missing argument."""

    def __init__(
        self,
        ctx: Context,
        args: list,
        arg_name: str,
        options: list[str],
        position: int,
        converter: Converter | None = None
    ):
        super().__init__(
            placeholder=f"Select a value for {arg_name!r}",
            options=[discord.SelectOption(label=option) for option in options]
        )
        self.ctx = ctx
        self.args = args
        self.position = position
        self.converter = converter

    async def callback(self, interaction: discord.Interaction) -> None:
        """re-invoke the context command with the completed argument value."""
        await interaction.response.defer()
        value = interaction.data["values"][0]
        if self.converter:
            value = await self.converter().convert(self.ctx, value)
        args = self.args.copy()  # This makes the view reusable.
        args.insert(self.position, value)
        log.trace(f"Argument filled with the value {value}. Re-invoking command")
        await self.ctx.invoke(self.ctx.command, *args)


class ArgumentCompletionView(discord.ui.View):
    """A view used to complete a missing argument in an in invoked command."""

    def __init__(
        self,
        ctx: Context,
        args: list,
        arg_name: str,
        options: list[str],
        position: int,
        converter: Converter | None = None
    ):
        super().__init__()
        log.trace(f"The {arg_name} argument was designated missing in the invocation {ctx.view.buffer!r}")
        self.add_item(ArgumentCompletionSelect(ctx, args, arg_name, options, position, converter))
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check to ensure that the interacting user is the user who invoked the command."""
        if interaction.user != self.ctx.author:
            embed = discord.Embed(description="Sorry, but this dropdown menu can only be used by the original author.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True


class CustomCallbackSelect(discord.ui.Select):
    """A selection which calls the provided callback on interaction."""

    def __init__(
        self,
        callback: Callable[[Interaction, discord.ui.Select], Coroutine[None]],
        *,
        custom_id: str = SELECT_MISSING,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        options: list[SelectOption] = SELECT_MISSING,
        disabled: bool = False,
        row: int | None = None,
    ):
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=options,
            disabled=disabled,
            row=row
        )
        self.custom_callback = callback

    async def callback(self, interaction: Interaction) -> Any:
        """Invoke the provided callback."""
        await self.custom_callback(interaction, self)


class BooleanSelectView(discord.ui.View):
    """A view containing an instance of BooleanSelect."""

    class BooleanSelect(discord.ui.Select):
        """Select a true or false value and send it to the supplied callback."""

        def __init__(self, setting_name: str, update_callback: Callable):
            super().__init__(options=[SelectOption(label="True"), SelectOption(label="False")])
            self.setting_name = setting_name
            self.update_callback = update_callback

        async def callback(self, interaction: Interaction) -> Any:
            """Respond to the interaction by sending the boolean value to the update callback."""
            value = self.values[0] == "True"
            await self.update_callback(setting_name=self.setting_name, setting_value=value)
            await interaction.response.edit_message(content=EDIT_CONFIRMED_MESSAGE.format(self.setting_name), view=None)

    def __init__(self, setting_name: str, update_callback: Callable):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.add_item(self.BooleanSelect(setting_name, update_callback))


class FreeInputModal(discord.ui.Modal):
    """A modal to freely enter a value for a setting."""

    def __init__(self, setting_name: str, type_: type, update_callback: Callable):
        title = f"{setting_name} Input" if len(setting_name) < MAX_MODAL_TITLE_LENGTH - 6 else "Setting Input"
        super().__init__(timeout=COMPONENT_TIMEOUT, title=title)

        self.setting_name = setting_name
        self.type_ = type_
        self.update_callback = update_callback

        label = setting_name if len(setting_name) < MAX_MODAL_TITLE_LENGTH else "Value"
        self.setting_input = discord.ui.TextInput(label=label, style=discord.TextStyle.paragraph, required=False)
        self.add_item(self.setting_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Update the setting with the new value in the embed."""
        try:
            if not self.setting_input.value:
                value = self.type_()
            else:
                value = self.type_(self.setting_input.value)
        except (ValueError, TypeError):
            await interaction.response.send_message(
                f"Could not process the input value for `{self.setting_name}`.", ephemeral=True
            )
        else:
            await self.update_callback(setting_name=self.setting_name, setting_value=value)
            await interaction.response.send_message(
                content=EDIT_CONFIRMED_MESSAGE.format(self.setting_name), ephemeral=True
            )


class SequenceEditView(discord.ui.View):
    """A view to modify the contents of a sequence of values."""

    class SingleItemModal(discord.ui.Modal):
        """A modal to enter a single list item."""

        new_item = discord.ui.TextInput(label="New Item")

        def __init__(self, view: SequenceEditView):
            super().__init__(title="Item Addition", timeout=COMPONENT_TIMEOUT)
            self.view = view

        async def on_submit(self, interaction: Interaction) -> None:
            """Send the submitted value to be added to the list."""
            await self.view.apply_addition(interaction, self.new_item.value)

    class NewListModal(discord.ui.Modal):
        """A modal to enter new contents for the list."""

        new_value = discord.ui.TextInput(label="Enter comma separated values", style=discord.TextStyle.paragraph)

        def __init__(self, view: SequenceEditView):
            super().__init__(title="New List", timeout=COMPONENT_TIMEOUT)
            self.view = view

        async def on_submit(self, interaction: Interaction) -> None:
            """Send the submitted value to be added to the list."""
            await self.view.apply_edit(interaction, self.new_value.value)

    def __init__(self, setting_name: str, starting_value: list, update_callback: Callable):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.setting_name = setting_name
        self.stored_value = starting_value
        self.update_callback = update_callback

        options = [SelectOption(label=item) for item in self.stored_value[:MAX_SELECT_ITEMS]]
        self.removal_select = CustomCallbackSelect(
            self.apply_removal, placeholder="Enter an item to remove", options=options, row=1
        )
        if self.stored_value:
            self.add_item(self.removal_select)

    async def apply_removal(self, interaction: Interaction, select: discord.ui.Select) -> None:
        """Remove an item from the list."""
        # The value might not be stored as a string.
        _i = len(self.stored_value)
        for _i, element in enumerate(self.stored_value):
            if str(element) == select.values[0]:
                break
        if _i != len(self.stored_value):
            self.stored_value.pop(_i)

        await interaction.response.edit_message(
            content=f"Current list: [{', '.join(self.stored_value)}]", view=self.copy()
        )
        self.stop()

    async def apply_addition(self, interaction: Interaction, item: str) -> None:
        """Add an item to the list."""
        if item in self.stored_value:  # Ignore duplicates
            await interaction.response.defer()
            return

        self.stored_value.append(item)
        await interaction.response.edit_message(
            content=f"Current list: [{', '.join(self.stored_value)}]", view=self.copy()
        )
        self.stop()

    async def apply_edit(self, interaction: Interaction, new_list: str) -> None:
        """Change the contents of the list."""
        self.stored_value = list(set(part.strip() for part in new_list.split(",") if part.strip()))
        await interaction.response.edit_message(
            content=f"Current list: [{', '.join(self.stored_value)}]", view=self.copy()
        )
        self.stop()

    @discord.ui.button(label="Add Value")
    async def add_value(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """A button to add an item to the list."""
        await interaction.response.send_modal(self.SingleItemModal(self))

    @discord.ui.button(label="Free Input")
    async def free_input(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """A button to change the entire list."""
        await interaction.response.send_modal(self.NewListModal(self))

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Send the final value to the embed editor."""
        # Edit first, it might time out otherwise.
        await self.update_callback(setting_name=self.setting_name, setting_value=self.stored_value)
        await interaction.response.edit_message(content=EDIT_CONFIRMED_MESSAGE.format(self.setting_name), view=None)
        self.stop()

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the list editing."""
        await interaction.response.edit_message(content="🚫 Canceled", view=None)
        self.stop()

    def copy(self) -> SequenceEditView:
        """Return a copy of this view."""
        return SequenceEditView(self.setting_name, self.stored_value, self.update_callback)


class EnumSelectView(discord.ui.View):
    """A view containing an instance of EnumSelect."""

    class EnumSelect(discord.ui.Select):
        """Select an enum value and send it to the supplied callback."""

        def __init__(self, setting_name: str, enum_cls: EnumMeta, update_callback: Callable):
            super().__init__(options=[SelectOption(label=elem.name) for elem in enum_cls])
            self.setting_name = setting_name
            self.enum_cls = enum_cls
            self.update_callback = update_callback

        async def callback(self, interaction: Interaction) -> Any:
            """Respond to the interaction by sending the enum value to the update callback."""
            await self.update_callback(setting_name=self.setting_name, setting_value=self.values[0])
            await interaction.response.edit_message(content=EDIT_CONFIRMED_MESSAGE.format(self.setting_name), view=None)

    def __init__(self, setting_name: str, enum_cls: EnumMeta, update_callback: Callable):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.add_item(self.EnumSelect(setting_name, enum_cls, update_callback))


class EditBaseView(ABC, discord.ui.View):
    """A view used to edit embed fields based on a provided type."""

    def __init__(self, author: discord.User):
        super().__init__(timeout=EDIT_TIMEOUT)
        self.author = author
        self.type_per_setting_name = {}

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Only allow interactions from the command invoker."""
        return interaction.user.id == self.author.id

    async def _prompt_new_value(self, interaction: Interaction, select: discord.ui.Select) -> None:
        """Prompt the user to give an override value for the setting they selected, and respond to the interaction."""
        setting_name = select.values[0]
        type_ = self.type_per_setting_name[setting_name]
        if origin := get_origin(type_):  # In case this is a types.GenericAlias or a typing._GenericAlias
            type_ = origin
        new_view = self.copy()
        # This is in order to not block the interaction response. There's a potential race condition here, since
        # a view's method is used without guaranteeing the task completed, but since it depends on user input
        # realistically it shouldn't happen.
        scheduling.create_task(interaction.message.edit(view=new_view))
        update_callback = partial(new_view.update_embed, interaction_or_msg=interaction.message)
        if type_ is bool:
            view = BooleanSelectView(setting_name, update_callback)
            await interaction.response.send_message(f"Choose a value for `{setting_name}`:", view=view, ephemeral=True)
        elif type_ in (set, list, tuple):
            if (current_value := self.current_value(setting_name)) is not MISSING:
                current_list = [str(elem) for elem in current_value]
            else:
                current_list = []
            await interaction.response.send_message(
                f"Current list: [{', '.join(current_list)}]",
                view=SequenceEditView(setting_name, current_list, update_callback),
                ephemeral=True
            )
        elif isinstance(type_, EnumMeta):
            view = EnumSelectView(setting_name, type_, update_callback)
            await interaction.response.send_message(f"Choose a value for `{setting_name}`:", view=view, ephemeral=True)
        else:
            await interaction.response.send_modal(FreeInputModal(setting_name, type_, update_callback))
        self.stop()

    @abstractmethod
    def current_value(self, setting_name: str) -> Any:
        """Get the current value stored for the setting or MISSING if none found."""

    @abstractmethod
    async def update_embed(self, interaction_or_msg: Interaction | discord.Message) -> None:
        """
        Update the embed with the new information.

        If `interaction_or_msg` is a Message, the invoking Interaction must be deferred before calling this function.
        """

    @abstractmethod
    def copy(self) -> EditBaseView:
        """Create a copy of this view."""


class DeleteConfirmationView(discord.ui.View):
    """A view to confirm a deletion."""

    def __init__(self, author: discord.Member | discord.User, callback: Callable):
        super().__init__(timeout=DELETION_TIMEOUT)
        self.author = author
        self.callback = callback

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Only allow interactions from the command invoker."""
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red, row=0)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Invoke the filter list deletion."""
        await interaction.response.edit_message(view=None)
        await self.callback()

    @discord.ui.button(label="Cancel", row=0)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the filter list deletion."""
        await interaction.response.edit_message(content="🚫 Operation canceled.", view=None)


class PhishConfirmationView(discord.ui.View):
    """Confirmation buttons for whether the alert was for a phishing attempt."""

    def __init__(
        self, mod: Member, offender: User | Member | None, phishing_content: str, target_filter_list: FilterList
    ):
        super().__init__()
        self.mod = mod
        self.offender = offender
        self.phishing_content = phishing_content
        self.target_filter_list = target_filter_list

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Only allow interactions from the command invoker."""
        return interaction.user.id == self.mod.id

    @discord.ui.button(label="Do it", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Auto-ban the user and add the phishing content to the appropriate filter list as an auto-ban filter."""
        await interaction.response.edit_message(view=None)

        if self.offender:
            compban_command = bot.instance.get_command("compban")
            if not compban_command:
                await interaction.followup.send(':warning: Could not find the command "compban".')
            else:
                ctx = FakeContext(interaction.message, interaction.channel, compban_command, author=self.mod)
                await compban_command(ctx, self.offender)

        compf_command = bot.instance.get_command("compfilter")
        if not compf_command:
            message = ':warning: Could not find the command "compfilter".'
            await interaction.followup.send(message)
        else:
            ctx = FakeContext(interaction.message, interaction.channel, compf_command)
            try:
                await compf_command(ctx, self.target_filter_list.name, self.phishing_content)
            except BadArgument as e:
                await interaction.followup.send(f":x: Could not add the filter: {e}")


    @discord.ui.button(label="Cancel")
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the operation."""
        new_message_content = f"~~{interaction.message.content}~~ 🚫 Operation canceled."
        await interaction.response.edit_message(content=new_message_content, view=None)

class PhishHandlingButton(discord.ui.Button):
    """
    A button that handles a phishing attempt.

    When pressed, ask for confirmation.
    If confirmed, comp-ban the offending user, and add the appropriate domain or invite as an auto-ban filter.
    """

    def __init__(self, offender: User | Member | None, phishing_content: str, target_filter_list: FilterList):
        super().__init__(emoji="🎣")
        self.offender = offender
        self.phishing_content = phishing_content
        self.target_filter_list = target_filter_list

    @lock_arg("phishing", "interaction", lambda interaction: interaction.message.id)
    async def callback(self, interaction: Interaction) -> Any:
        """Ask for confirmation for handling the phish."""
        message_content = f"{interaction.user.mention} Is this a phishing attempt? "
        if self.offender:
            message_content += f"The user {self.offender.mention} will be comp-banned, and "
        else:
            message_content += "The user was not found, but "
        message_content += (
            f"`{escape_markdown(self.phishing_content)}` will be added as an auto-ban filter to the "
            f"denied *{self.target_filter_list.name}s* list."
        )
        confirmation_view = PhishConfirmationView(
            interaction.user, self.offender, self.phishing_content, self.target_filter_list
        )
        await interaction.response.send_message(message_content, view=confirmation_view)


class AlertView(discord.ui.View):
    """A view providing info about the offending user."""

    def __init__(self, ctx: FilterContext, triggered_filters: dict[FilterList, list[str]] | None = None):
        super().__init__(timeout=ALERT_VIEW_TIMEOUT)
        self.ctx = ctx
        if "banned" in self.ctx.action_descriptions:
            # If the user has already been banned, do not attempt to add phishing button since the URL or guild invite
            # is probably already added as a filter
            return
        phishing_content, target_filter_list =  self._extract_potential_phish(triggered_filters)
        if phishing_content:
            self.add_item(PhishHandlingButton(ctx.author, phishing_content, target_filter_list))

    @discord.ui.button(label="ID")
    async def user_id(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Reply with the ID of the offending user."""
        await interaction.response.send_message(self.ctx.author.id, ephemeral=True)

    @discord.ui.button(emoji="👤")
    async def user_info(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Send the info embed of the offending user."""
        command = bot.instance.get_command("user")
        if not command:
            await interaction.response.send_message("The command `user` is not loaded.", ephemeral=True)
            return

        await interaction.response.defer()
        fake_ctx = FakeContext(interaction.message, interaction.channel, command, author=interaction.user)
        # Get the most updated user/member object every time the button is pressed.
        author = await get_or_fetch_member(interaction.guild, self.ctx.author.id)
        if author is None:
            author = await bot.instance.fetch_user(self.ctx.author.id)
        await command(fake_ctx, author)

    @discord.ui.button(emoji="🗒️")
    async def user_infractions(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Send the infractions embed of the offending user."""
        command = bot.instance.get_command("infraction search")
        if not command:
            await interaction.response.send_message("The command `infraction search` is not loaded.", ephemeral=True)
            return

        await interaction.response.defer()
        fake_ctx = FakeContext(interaction.message, interaction.channel, command, author=interaction.user)
        await command(fake_ctx, self.ctx.author)

    def _extract_potential_phish(
        self, triggered_filters: dict[FilterList, list[str]] | None
    ) -> tuple[str, FilterList | None]:
        """
        Check if the alert is potentially for phishing.

        If it is, return the phishing content and the filter list to add it to.
        Otherwise, return an empty string and None.

        A potential phish is a message event where a single invite or domain is found, and nothing else.
        Everyone filters are an exception.
        """
        if self.ctx.event != Event.MESSAGE or not self.ctx.potential_phish:
            return "", None

        if triggered_filters:
            for filter_list, messages in triggered_filters.items():
                if messages and (filter_list.name != "unique" or len(messages) > 1 or "everyone" not in messages[0]):
                    return "", None

        encountered = False
        content = ""
        target_filter_list = None
        for filter_list, content_list in self.ctx.potential_phish.items():
            if len(content_list) > 1:
                return "", None
            if content_list:
                current_content = next(iter(content_list))
                if filter_list.name == "domain" and re.fullmatch(DISCORD_INVITE, current_content):
                    # Leave invites to the invite filterlist.
                    continue
                if encountered:
                    return "", None
                target_filter_list = filter_list
                content = current_content
                encountered = True

        if encountered:
            return content, target_filter_list
        return "", None
