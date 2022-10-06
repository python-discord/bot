from __future__ import annotations

import re
from enum import EnumMeta
from functools import partial
from typing import Any, Callable, Coroutine, Optional, TypeVar, Union

import discord
import discord.ui
from botcore.site_api import ResponseCodeError
from botcore.utils import scheduling
from discord import Embed, Interaction, User
from discord.ext.commands import BadArgument, Context
from discord.ui.select import MISSING, SelectOption

from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._utils import to_serializable
from bot.log import get_logger

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
# Max length of modal text component label
MAX_MODAL_LABEL_LENGTH = 45
# Max number of items in a select
MAX_SELECT_ITEMS = 25
MAX_EMBED_DESCRIPTION = 4000

T = TypeVar('T')


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


def build_filter_repr_dict(
    filter_list: FilterList,
    list_type: ListType,
    filter_type: type[Filter],
    settings_overrides: dict,
    extra_fields_overrides: dict
) -> dict:
    """Build a dictionary of field names and values to pass to `_build_embed_from_dict`."""
    # Get filter list settings
    default_setting_values = {}
    for type_ in ("actions", "validations"):
        for _, setting in filter_list.defaults[list_type][type_].items():
            default_setting_values.update(to_serializable(setting.dict()))

    # Add overrides. It's done in this way to preserve field order, since the filter won't have all settings.
    total_values = {}
    for name, value in default_setting_values.items():
        if name not in settings_overrides:
            total_values[name] = value
        else:
            total_values[f"{name}*"] = settings_overrides[name]

    # Add the filter-specific settings.
    if filter_type.extra_fields_type:
        # This iterates over the default values of the extra fields model.
        for name, value in filter_type.extra_fields_type().dict().items():
            if name not in extra_fields_overrides:
                total_values[f"{filter_type.name}/{name}"] = value
            else:
                total_values[f"{filter_type.name}/{name}*"] = value

    return total_values


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


class CustomCallbackSelect(discord.ui.Select):
    """A selection which calls the provided callback on interaction."""

    def __init__(
        self,
        callback: Callable[[Interaction, discord.ui.Select], Coroutine[None]],
        *,
        custom_id: str = MISSING,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        options: list[SelectOption] = MISSING,
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


class EditContentModal(discord.ui.Modal, title="Edit Content"):
    """A modal to input a filter's content."""

    content = discord.ui.TextInput(label="Content")

    def __init__(self, embed_view: SettingsEditView, message: discord.Message):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.embed_view = embed_view
        self.message = message

    async def on_submit(self, interaction: Interaction) -> None:
        """Update the embed with the new content."""
        await interaction.response.defer()
        await self.embed_view.update_embed(self.message, content=self.content.value)


class EditDescriptionModal(discord.ui.Modal, title="Edit Description"):
    """A modal to input a filter's description."""

    description = discord.ui.TextInput(label="Description")

    def __init__(self, embed_view: SettingsEditView, message: discord.Message):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.embed_view = embed_view
        self.message = message

    async def on_submit(self, interaction: Interaction) -> None:
        """Update the embed with the new description."""
        await interaction.response.defer()
        await self.embed_view.update_embed(self.message, description=self.description.value)


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
            value = self.type_(self.setting_input.value) or None
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

    def __init__(self, setting_name: str, starting_value: list, type_: type, update_callback: Callable):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.setting_name = setting_name
        self.stored_value = starting_value
        self.type_ = type_
        self.update_callback = update_callback

        options = [SelectOption(label=item) for item in starting_value[:MAX_SELECT_ITEMS]]
        self.removal_select = CustomCallbackSelect(
            self.apply_removal, placeholder="Enter an item to remove", options=options, row=1
        )
        if starting_value:
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
        self.stored_value.append(item)
        self.removal_select.options = [SelectOption(label=item) for item in self.stored_value[:MAX_SELECT_ITEMS]]
        if len(self.stored_value) == 1:
            self.add_item(self.removal_select)
        await interaction.response.edit_message(content=f"Current list: {self.stored_value}", view=self)

    async def apply_edit(self, interaction: Interaction, new_list: str) -> None:
        """Change the contents of the list."""
        self.stored_value = new_list.split(",")
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


class SettingsEditView(discord.ui.View):
    """A view used to edit a filter's settings before updating the database."""

    class _REMOVE:
        """Sentinel value for when an override should be removed."""

    def __init__(
        self,
        filter_list: FilterList,
        list_type: ListType,
        filter_type: type[Filter],
        content: str | None,
        description: str | None,
        settings_overrides: dict,
        filter_settings_overrides: dict,
        loaded_settings: dict,
        loaded_filter_settings: dict,
        author: User,
        embed: Embed,
        confirm_callback: Callable
    ):
        super().__init__(timeout=EDIT_TIMEOUT)
        self.filter_list = filter_list
        self.list_type = list_type
        self.filter_type = filter_type
        self.content = content
        self.description = description
        self.settings_overrides = settings_overrides
        self.filter_settings_overrides = filter_settings_overrides
        self.loaded_settings = loaded_settings
        self.loaded_filter_settings = loaded_filter_settings
        self.author = author
        self.embed = embed
        self.confirm_callback = confirm_callback

        all_settings_repr_dict = build_filter_repr_dict(
            filter_list, list_type, filter_type, settings_overrides, filter_settings_overrides
        )
        populate_embed_from_dict(embed, all_settings_repr_dict)

        self.type_per_setting_name = {setting: info[2] for setting, info in loaded_settings.items()}
        self.type_per_setting_name.update({
            f"{filter_type.name}/{name}": type_
            for name, (_, _, type_) in loaded_filter_settings.get(filter_type.name, {}).items()
        })

        add_select = CustomCallbackSelect(
            self._prompt_new_override,
            placeholder="Select a setting to edit",
            options=[SelectOption(label=name) for name in sorted(self.type_per_setting_name)],
            row=1
        )
        self.add_item(add_select)

        override_names = (
            list(settings_overrides) + [f"{filter_list.name}/{setting}" for setting in filter_settings_overrides]
        )
        remove_select = CustomCallbackSelect(
            self._remove_override,
            placeholder="Select an override to remove",
            options=[SelectOption(label=name) for name in sorted(override_names)],
            row=2
        )
        if remove_select.options:
            self.add_item(remove_select)

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Only allow interactions from the command invoker."""
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Edit Content", row=3)
    async def edit_content(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """A button to edit the filter's content. Pressing the button invokes a modal."""
        modal = EditContentModal(self, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Description", row=3)
    async def edit_description(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """A button to edit the filter's description. Pressing the button invokes a modal."""
        modal = EditDescriptionModal(self, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Empty Description", row=3)
    async def empty_description(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """A button to empty the filter's description."""
        await self.update_embed(interaction, description=self._REMOVE)

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green, row=4)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Confirm the content, description, and settings, and update the filters database."""
        if self.content is None:
            await interaction.response.send_message(
                ":x: Cannot add a filter with no content.", ephemeral=True, reference=interaction.message
            )
        if self.description is None:
            self.description = ""
        await interaction.response.edit_message(view=None)  # Make sure the interaction succeeds first.
        try:
            await self.confirm_callback(
                interaction.message,
                self.filter_list,
                self.list_type,
                self.filter_type,
                self.content,
                self.description,
                self.settings_overrides,
                self.filter_settings_overrides
            )
        except ResponseCodeError as e:
            await interaction.message.reply(embed=format_response_error(e))
            await interaction.message.edit(view=self)
        except ValueError as e:
            await interaction.message.reply(
                embed=Embed(colour=discord.Colour.red(), title="Bad Content", description=str(e))
            )
            await interaction.message.edit(view=self)
        else:
            self.stop()

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.red, row=4)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the operation."""
        await interaction.response.edit_message(content="🚫 Operation canceled.", embed=None, view=None)
        self.stop()

    async def _prompt_new_override(self, interaction: Interaction, select: discord.ui.Select) -> None:
        """Prompt the user to give an override value for the setting they selected, and respond to the interaction."""
        setting_name = select.values[0]
        type_ = self.type_per_setting_name[setting_name]
        is_optional, type_ = _remove_optional(type_)
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
            current_value = self.settings_overrides.get(setting_name, [])
            await interaction.response.send_message(
                f"Current list: {current_value}",
                view=SequenceEditView(setting_name, current_value, type_, update_callback),
                ephemeral=True
            )
        elif isinstance(type_, EnumMeta):
            view = EnumSelectView(setting_name, type_, update_callback)
            await interaction.response.send_message(f"Choose a value for `{setting_name}`:", view=view, ephemeral=True)
        else:
            await interaction.response.send_modal(FreeInputModal(setting_name, not is_optional, type_, update_callback))
        self.stop()

    async def update_embed(
        self,
        interaction_or_msg: discord.Interaction | discord.Message,
        *,
        content: str | None = None,
        description: str | type[SettingsEditView._REMOVE] | None = None,
        setting_name: str | None = None,
        setting_value: str | type[SettingsEditView._REMOVE] | None = None,
    ) -> None:
        """
        Update the embed with the new information.

        If a setting name is provided with a _REMOVE value, remove the override.
        If `interaction_or_msg` is a Message, the invoking Interaction must be deferred before calling this function.
        """
        if content is not None or description is not None:
            if content is not None:
                self.content = content
            else:
                content = self.content  # If there's no content or description, use the existing values.
            if description is self._REMOVE:
                self.description = None
            elif description is not None:
                self.description = description
            else:
                description = self.description

            # Update the embed with the new content and/or description.
            self.embed.description = f"`{content}`" if content else "*No content*"
            if description and description is not self._REMOVE:
                self.embed.description += f" - {description}"

        if setting_name:
            # Find the right dictionary to update.
            if "/" in setting_name:
                filter_name, setting_name = setting_name.split("/", maxsplit=1)
                dict_to_edit = self.filter_settings_overrides
            else:
                dict_to_edit = self.settings_overrides
            # Update the setting override value or remove it
            if setting_value is not self._REMOVE:
                dict_to_edit[setting_name] = setting_value
            elif setting_name in dict_to_edit:
                del dict_to_edit[setting_name]

        # This is inefficient, but otherwise the selects go insane if the user attempts to edit the same setting
        # multiple times, even when replacing the select with a new one.
        self.embed.clear_fields()
        new_view = self.copy()

        try:
            if isinstance(interaction_or_msg, discord.Interaction):
                await interaction_or_msg.response.edit_message(embed=self.embed, view=new_view)
            else:
                await interaction_or_msg.edit(embed=self.embed, view=new_view)
        except discord.errors.HTTPException:  # Various error such as embed description being too long.
            pass
        else:
            self.stop()

    async def edit_setting_override(self, interaction: Interaction, setting_name: str, override_value: Any) -> None:
        """
        Update the overrides with the new value and edit the embed.

        The interaction needs to be the selection of the setting attached to the embed.
        """
        await self.update_embed(interaction, setting_name=setting_name, setting_value=override_value)

    async def _remove_override(self, interaction: Interaction, select: discord.ui.Select) -> None:
        """
        Remove the override for the setting the user selected, and edit the embed.

        The interaction needs to be the selection of the setting attached to the embed.
        """
        await self.update_embed(interaction, setting_name=select.values[0], setting_value=self._REMOVE)

    def copy(self) -> SettingsEditView:
        """Create a copy of this view."""
        return SettingsEditView(
            self.filter_list,
            self.list_type,
            self.filter_type,
            self.content,
            self.description,
            self.settings_overrides,
            self.filter_settings_overrides,
            self.loaded_settings,
            self.loaded_filter_settings,
            self.author,
            self.embed,
            self.confirm_callback
        )


def _remove_optional(type_: type) -> tuple[bool, type]:
    """Return whether the type is Optional, and the Union of types which aren't None."""
    if not hasattr(type_, "__args__"):
        return False, type_
    args = list(type_.__args__)
    if type(None) not in args:
        return False, type_
    args.remove(type(None))
    return True, Union[tuple(args)]


def _parse_value(value: str, type_: type[T]) -> T:
    """Parse the value and attempt to convert it to the provided type."""
    is_optional, type_ = _remove_optional(type_)
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


def description_and_settings_converter(
    list_name: str, loaded_settings: dict, loaded_filter_settings: dict, input_data: str
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Parse a string representing a possible description and setting overrides, and validate the setting names."""
    if not input_data:
        return "", {}, {}

    settings_pattern = re.compile(r"\s+(?=\S+=\S+)")
    single_setting_pattern = re.compile(r"\w+=.+")

    parsed = settings_pattern.split(input_data)
    if not parsed:
        return "", {}, {}

    description = ""
    if not single_setting_pattern.match(parsed[0]):
        description, *parsed = parsed

    settings = {setting: value for setting, value in [part.split("=", maxsplit=1) for part in parsed]}

    filter_settings = {}
    for setting, _ in list(settings.items()):
        if setting not in loaded_settings:
            if "/" in setting:
                setting_list_name, filter_setting_name = setting.split("/", maxsplit=1)
                if setting_list_name.lower() != list_name.lower():
                    raise BadArgument(
                        f"A setting for a {setting_list_name!r} filter was provided, but the list name is {list_name!r}"
                    )
                if filter_setting_name not in loaded_filter_settings[list_name]:
                    raise BadArgument(f"{setting!r} is not a recognized setting.")
                type_ = loaded_filter_settings[list_name][filter_setting_name][2]
                try:
                    filter_settings[filter_setting_name] = _parse_value(settings.pop(setting), type_)
                except (TypeError, ValueError) as e:
                    raise BadArgument(e)
            else:
                raise BadArgument(f"{setting!r} is not a recognized setting.")
        else:
            type_ = loaded_settings[setting][2]
            try:
                settings[setting] = _parse_value(settings.pop(setting), type_)
            except (TypeError, ValueError) as e:
                raise BadArgument(e)

    return description, settings, filter_settings


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
