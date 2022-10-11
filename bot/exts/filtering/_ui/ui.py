from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import EnumMeta
from functools import partial
from typing import Any, Callable, Coroutine, Optional, TypeVar, Union

import discord
from botcore.site_api import ResponseCodeError
from botcore.utils import scheduling
from botcore.utils.logging import get_logger
from discord import Embed, Interaction
from discord.ext.commands import Context
from discord.ui.select import MISSING as SELECT_MISSING, SelectOption

log = get_logger(__name__)


# Max number of characters in a Discord embed field value, minus 6 characters for a placeholder.
MAX_FIELD_SIZE = 1018
# Max number of characters for an embed field's value before it should take its own line.
MAX_INLINE_SIZE = 50
# Number of seconds before a settings editing view timeout.
EDIT_TIMEOUT = 600
# Number of seconds before timeout of an editing component.
COMPONENT_TIMEOUT = 180
# Max length of modal title
MAX_MODAL_TITLE_LENGTH = 45
# Max number of items in a select
MAX_SELECT_ITEMS = 25
MAX_EMBED_DESCRIPTION = 4000

SETTINGS_DELIMITER = re.compile(r"\s+(?=\S+=\S+)")
SINGLE_SETTING_PATTERN = re.compile(r"\w+=.+")

# Sentinel value to denote that a value is missing
MISSING = object()

T = TypeVar('T')


def populate_embed_from_dict(embed: Embed, data: dict) -> None:
    """Populate a Discord embed by populating fields from the given dict."""
    for setting, value in data.items():
        if setting.startswith("_"):
            continue
        if type(value) in (set, tuple):
            value = list(value)
        value = str(value) if value not in ("", None) else "-"
        if len(value) > MAX_FIELD_SIZE:
            value = value[:MAX_FIELD_SIZE] + " [...]"
        embed.add_field(name=setting, value=value, inline=len(value) < MAX_INLINE_SIZE)


def remove_optional(type_: type) -> tuple[bool, type]:
    """Return whether the type is Optional, and the Union of types which aren't None."""
    if not hasattr(type_, "__args__"):
        return False, type_
    args = list(type_.__args__)
    if type(None) not in args:
        return False, type_
    args.remove(type(None))
    return True, Union[tuple(args)]


def parse_value(value: str, type_: type[T]) -> T:
    """Parse the value and attempt to convert it to the provided type."""
    is_optional, type_ = remove_optional(type_)
    if is_optional and value == '""':
        return None
    if hasattr(type_, "__origin__"):  # In case this is a types.GenericAlias or a typing._GenericAlias
        type_ = type_.__origin__
    if type_ in (tuple, list, set):
        return type_(value.split(","))
    if type_ is bool:
        return value == "True"
    if isinstance(type_, EnumMeta):
        return type_[value.upper()]

    return type_(value)


def format_response_error(e: ResponseCodeError) -> Embed:
    """Format the response error into an embed."""
    description = ""
    if "non_field_errors" in e.response_json:
        non_field_errors = e.response_json.pop("non_field_errors")
        description += "\n".join(f"• {error}" for error in non_field_errors) + "\n"
    for field, errors in e.response_json.items():
        description += "\n".join(f"• {field} - {error}" for error in errors) + "\n"
    description = description.strip()
    if len(description) > MAX_EMBED_DESCRIPTION:
        description = description[:MAX_EMBED_DESCRIPTION] + "[...]"

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
        converter: Optional[Callable] = None
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
            value = self.converter(value)
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
        converter: Optional[Callable] = None
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
            await interaction.response.edit_message(content="✅ Edit confirmed", view=None)
            value = self.values[0] == "True"
            await self.update_callback(setting_name=self.setting_name, setting_value=value)

    def __init__(self, setting_name: str, update_callback: Callable):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.add_item(self.BooleanSelect(setting_name, update_callback))


class FreeInputModal(discord.ui.Modal):
    """A modal to freely enter a value for a setting."""

    def __init__(self, setting_name: str, required: bool, type_: type, update_callback: Callable):
        title = f"{setting_name} Input" if len(setting_name) < MAX_MODAL_TITLE_LENGTH - 6 else "Setting Input"
        super().__init__(timeout=COMPONENT_TIMEOUT, title=title)

        self.setting_name = setting_name
        self.type_ = type_
        self.update_callback = update_callback

        label = setting_name if len(setting_name) < MAX_MODAL_TITLE_LENGTH else "Value"
        self.setting_input = discord.ui.TextInput(label=label, style=discord.TextStyle.paragraph, required=required)
        self.add_item(self.setting_input)

    async def on_submit(self, interaction: Interaction) -> None:
        """Update the setting with the new value in the embed."""
        try:
            value = self.type_(self.setting_input.value)
        except (ValueError, TypeError):
            await interaction.response.send_message(
                f"Could not process the input value for `{self.setting_name}`.", ephemeral=True
            )
        else:
            await interaction.response.defer()
            await self.update_callback(setting_name=self.setting_name, setting_value=value)


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

        select.options = [SelectOption(label=item) for item in self.stored_value[:MAX_SELECT_ITEMS]]
        if not self.stored_value:
            self.remove_item(self.removal_select)
        await interaction.response.edit_message(content=f"Current list: {self.stored_value}", view=self)

    async def apply_addition(self, interaction: Interaction, item: str) -> None:
        """Add an item to the list."""
        if item in self.stored_value:  # Ignore duplicates
            await interaction.response.defer()
            return

        self.stored_value.append(item)
        self.removal_select.options = [SelectOption(label=item) for item in self.stored_value[:MAX_SELECT_ITEMS]]
        if len(self.stored_value) == 1:
            self.add_item(self.removal_select)
        await interaction.response.edit_message(content=f"Current list: {self.stored_value}", view=self)

    async def apply_edit(self, interaction: Interaction, new_list: str) -> None:
        """Change the contents of the list."""
        self.stored_value = list(set(new_list.split(",")))
        self.removal_select.options = [SelectOption(label=item) for item in self.stored_value[:MAX_SELECT_ITEMS]]
        if len(self.stored_value) == 1:
            self.add_item(self.removal_select)
        await interaction.response.edit_message(content=f"Current list: {self.stored_value}", view=self)

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
        await interaction.response.edit_message(content="✅ Edit confirmed", view=None)
        await self.update_callback(setting_name=self.setting_name, setting_value=self.stored_value)
        self.stop()

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the list editing."""
        await interaction.response.edit_message(content="🚫 Canceled", view=None)
        self.stop()


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
            await interaction.response.edit_message(content="✅ Edit confirmed", view=None)
            await self.update_callback(setting_name=self.setting_name, setting_value=self.values[0])

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
        is_optional, type_ = remove_optional(type_)
        if hasattr(type_, "__origin__"):  # In case this is a types.GenericAlias or a typing._GenericAlias
            type_ = type_.__origin__
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
                current_list = list(current_value)
            else:
                current_list = []
            await interaction.response.send_message(
                f"Current list: {current_list}",
                view=SequenceEditView(setting_name, current_list, update_callback),
                ephemeral=True
            )
        elif isinstance(type_, EnumMeta):
            view = EnumSelectView(setting_name, type_, update_callback)
            await interaction.response.send_message(f"Choose a value for `{setting_name}`:", view=view, ephemeral=True)
        else:
            await interaction.response.send_modal(FreeInputModal(setting_name, not is_optional, type_, update_callback))
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
