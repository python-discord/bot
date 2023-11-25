from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord
import discord.ui
from discord import Embed, Interaction, User
from discord.ext.commands import BadArgument
from discord.ui.select import SelectOption
from pydis_core.site_api import ResponseCodeError

from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._ui.ui import (
    COMPONENT_TIMEOUT,
    CustomCallbackSelect,
    EditBaseView,
    MAX_EMBED_DESCRIPTION,
    MISSING,
    SETTINGS_DELIMITER,
    SINGLE_SETTING_PATTERN,
    format_response_error,
    parse_value,
    populate_embed_from_dict,
)
from bot.exts.filtering._utils import repr_equals, to_serializable
from bot.log import get_logger

log = get_logger(__name__)


def build_filter_repr_dict(
    filter_list: FilterList,
    list_type: ListType,
    filter_type: type[Filter],
    settings_overrides: dict,
    extra_fields_overrides: dict
) -> dict:
    """Build a dictionary of field names and values to pass to `populate_embed_from_dict`."""
    # Get filter list settings
    default_setting_values = {}
    for settings_group in filter_list[list_type].defaults:
        for _, setting in settings_group.items():
            default_setting_values.update(to_serializable(setting.model_dump(), ui_repr=True))

    # Add overrides. It's done in this way to preserve field order, since the filter won't have all settings.
    total_values = {}
    for name, value in default_setting_values.items():
        if name not in settings_overrides or repr_equals(settings_overrides[name], value):
            total_values[name] = value
        else:
            total_values[f"{name}*"] = settings_overrides[name]

    # Add the filter-specific settings.
    if filter_type.extra_fields_type:
        # This iterates over the default values of the extra fields model.
        for name, value in filter_type.extra_fields_type().model_dump().items():
            if name not in extra_fields_overrides or repr_equals(extra_fields_overrides[name], value):
                total_values[f"{filter_type.name}/{name}"] = value
            else:
                total_values[f"{filter_type.name}/{name}*"] = extra_fields_overrides[name]

    return total_values


class EditContentModal(discord.ui.Modal, title="Edit Content"):
    """A modal to input a filter's content."""

    content = discord.ui.TextInput(label="Content")

    def __init__(self, embed_view: FilterEditView, message: discord.Message):
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

    def __init__(self, embed_view: FilterEditView, message: discord.Message):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.embed_view = embed_view
        self.message = message

    async def on_submit(self, interaction: Interaction) -> None:
        """Update the embed with the new description."""
        await interaction.response.defer()
        await self.embed_view.update_embed(self.message, description=self.description.value)


class TemplateModal(discord.ui.Modal, title="Template"):
    """A modal to enter a filter ID to copy its overrides over."""

    template = discord.ui.TextInput(label="Template Filter ID")

    def __init__(self, embed_view: FilterEditView, message: discord.Message):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.embed_view = embed_view
        self.message = message

    async def on_submit(self, interaction: Interaction) -> None:
        """Update the embed with the new description."""
        await self.embed_view.apply_template(self.template.value, self.message, interaction)


class FilterEditView(EditBaseView):
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
        super().__init__(author)
        self.filter_list = filter_list
        self.list_type = list_type
        self.filter_type = filter_type
        self.content = content
        self.description = description
        self.settings_overrides = settings_overrides
        self.filter_settings_overrides = filter_settings_overrides
        self.loaded_settings = loaded_settings
        self.loaded_filter_settings = loaded_filter_settings
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
            self._prompt_new_value,
            placeholder="Select a setting to edit",
            options=[SelectOption(label=name) for name in sorted(self.type_per_setting_name)],
            row=1
        )
        self.add_item(add_select)

        if settings_overrides or filter_settings_overrides:
            override_names = (
                list(settings_overrides) + [f"{filter_list.name}/{setting}" for setting in filter_settings_overrides]
            )
            remove_select = CustomCallbackSelect(
                self._remove_override,
                placeholder="Select an override to remove",
                options=[SelectOption(label=name) for name in sorted(override_names)],
                row=2
            )
            self.add_item(remove_select)

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

    @discord.ui.button(label="Template", row=3)
    async def enter_template(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """A button to enter a filter template ID and copy its overrides over."""
        modal = TemplateModal(self, interaction.message)
        await interaction.response.send_modal(modal)

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
        except BadArgument as e:
            await interaction.message.reply(
                embed=Embed(colour=discord.Colour.red(), title="Bad Argument", description=str(e))
            )
            await interaction.message.edit(view=self)
        else:
            self.stop()

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.red, row=4)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the operation."""
        await interaction.response.edit_message(content="🚫 Operation canceled.", embed=None, view=None)
        self.stop()

    def current_value(self, setting_name: str) -> Any:
        """Get the current value stored for the setting or MISSING if none found."""
        if setting_name in self.settings_overrides:
            return self.settings_overrides[setting_name]
        if "/" in setting_name:
            _, setting_name = setting_name.split("/", maxsplit=1)
            if setting_name in self.filter_settings_overrides:
                return self.filter_settings_overrides[setting_name]
        return MISSING

    async def update_embed(
        self,
        interaction_or_msg: discord.Interaction | discord.Message,
        *,
        content: str | None = None,
        description: str | type[FilterEditView._REMOVE] | None = None,
        setting_name: str | None = None,
        setting_value: str | type[FilterEditView._REMOVE] | None = None,
    ) -> None:
        """
        Update the embed with the new information.

        If a setting name is provided with a _REMOVE value, remove the override.
        If `interaction_or_msg` is a Message, the invoking Interaction must be deferred before calling this function.
        """
        if content is not None or description is not None:
            if content is not None:
                filter_type = self.filter_list.get_filter_type(content)
                if not filter_type:
                    if isinstance(interaction_or_msg, discord.Message):
                        send_method = interaction_or_msg.channel.send
                    else:
                        send_method = interaction_or_msg.response.send_message
                    await send_method(f":x: Could not find a filter type appropriate for `{content}`.")
                    return
                self.content = content
                self.filter_type = filter_type
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
            if len(self.embed.description) > MAX_EMBED_DESCRIPTION:
                self.embed.description = self.embed.description[:MAX_EMBED_DESCRIPTION - 5] + "[...]"

        if setting_name:
            # Find the right dictionary to update.
            if "/" in setting_name:
                filter_name, setting_name = setting_name.split("/", maxsplit=1)
                dict_to_edit = self.filter_settings_overrides
                default_value = self.filter_type.extra_fields_type().model_dump()[setting_name]
            else:
                dict_to_edit = self.settings_overrides
                default_value = self.filter_list[self.list_type].default(setting_name)
            # Update the setting override value or remove it
            if setting_value is not self._REMOVE:
                if not repr_equals(setting_value, default_value):
                    dict_to_edit[setting_name] = setting_value
                # If there's already an override, remove it, since the new value is the same as the default.
                elif setting_name in dict_to_edit:
                    dict_to_edit.pop(setting_name)
            elif setting_name in dict_to_edit:
                dict_to_edit.pop(setting_name)

        # This is inefficient, but otherwise the selects go insane if the user attempts to edit the same setting
        # multiple times, even when replacing the select with a new one.
        self.embed.clear_fields()
        new_view = self.copy()

        try:
            if isinstance(interaction_or_msg, discord.Interaction):
                await interaction_or_msg.response.edit_message(embed=self.embed, view=new_view)
            else:
                await interaction_or_msg.edit(embed=self.embed, view=new_view)
        except discord.errors.HTTPException:  # Various unexpected errors.
            pass
        else:
            self.stop()

    async def edit_setting_override(self, interaction: Interaction, setting_name: str, override_value: Any) -> None:
        """
        Update the overrides with the new value and edit the embed.

        The interaction needs to be the selection of the setting attached to the embed.
        """
        await self.update_embed(interaction, setting_name=setting_name, setting_value=override_value)

    async def apply_template(self, template_id: str, embed_message: discord.Message, interaction: Interaction) -> None:
        """Replace any non-overridden settings with overrides from the given filter."""
        try:
            settings, filter_settings = template_settings(
                template_id, self.filter_list, self.list_type, self.filter_type
            )
        except BadArgument as e:  # The interaction object is necessary to send an ephemeral message.
            await interaction.response.send_message(f":x: {e}", ephemeral=True)
            return
        else:
            await interaction.response.defer()

        self.settings_overrides = settings | self.settings_overrides
        self.filter_settings_overrides = filter_settings | self.filter_settings_overrides
        self.embed.clear_fields()
        await embed_message.edit(embed=self.embed, view=self.copy())
        self.stop()

    async def _remove_override(self, interaction: Interaction, select: discord.ui.Select) -> None:
        """
        Remove the override for the setting the user selected, and edit the embed.

        The interaction needs to be the selection of the setting attached to the embed.
        """
        await self.update_embed(interaction, setting_name=select.values[0], setting_value=self._REMOVE)

    def copy(self) -> FilterEditView:
        """Create a copy of this view."""
        return FilterEditView(
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


def description_and_settings_converter(
    filter_list: FilterList,
    list_type: ListType,
    filter_type: type[Filter],
    loaded_settings: dict,
    loaded_filter_settings: dict,
    input_data: str
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Parse a string representing a possible description and setting overrides, and validate the setting names."""
    if not input_data:
        return "", {}, {}

    parsed = SETTINGS_DELIMITER.split(input_data)
    if not parsed:
        return "", {}, {}

    description = ""
    if not SINGLE_SETTING_PATTERN.match(parsed[0]):
        description, *parsed = parsed

    settings = {setting: value for setting, value in [part.split("=", maxsplit=1) for part in parsed]}  # noqa: C416
    template = None
    if "--template" in settings:
        template = settings.pop("--template")

    filter_settings = {}
    for setting, _ in list(settings.items()):
        if setting in loaded_settings:  # It's a filter list setting
            type_ = loaded_settings[setting][2]
            try:
                parsed_value = parse_value(settings.pop(setting), type_)
                if not repr_equals(parsed_value, filter_list[list_type].default(setting)):
                    settings[setting] = parsed_value
            except (TypeError, ValueError) as e:
                raise BadArgument(e)
        elif "/" not in setting:
            raise BadArgument(f"{setting!r} is not a recognized setting.")
        else:  # It's a filter setting
            filter_name, filter_setting_name = setting.split("/", maxsplit=1)
            if filter_name.lower() != filter_type.name.lower():
                raise BadArgument(
                    f"A setting for a {filter_name!r} filter was provided, but the filter name is {filter_type.name!r}"
                )
            if filter_setting_name not in loaded_filter_settings[filter_type.name]:
                raise BadArgument(f"{setting!r} is not a recognized setting.")
            type_ = loaded_filter_settings[filter_type.name][filter_setting_name][2]
            try:
                parsed_value = parse_value(settings.pop(setting), type_)
                if not repr_equals(parsed_value, getattr(filter_type.extra_fields_type(), filter_setting_name)):
                    filter_settings[filter_setting_name] = parsed_value
            except (TypeError, ValueError) as e:
                raise BadArgument(e)

    # Pull templates settings and apply them.
    if template is not None:
        try:
            t_settings, t_filter_settings = template_settings(template, filter_list, list_type, filter_type)
        except ValueError as e:
            raise BadArgument(str(e))
        else:
            # The specified settings go on top of the template
            settings = t_settings | settings
            filter_settings = t_filter_settings | filter_settings

    return description, settings, filter_settings


def filter_overrides_for_ui(filter_: Filter) -> tuple[dict, dict]:
    """Get the filter's overrides in a format that can be displayed in the UI."""
    overrides_values, extra_fields_overrides = filter_.overrides
    return to_serializable(overrides_values, ui_repr=True), to_serializable(extra_fields_overrides, ui_repr=True)


def template_settings(
    filter_id: str, filter_list: FilterList, list_type: ListType, filter_type: type[Filter]
) -> tuple[dict, dict]:
    """Find the filter with specified ID, and return its settings."""
    try:
        filter_id = int(filter_id)
        if filter_id < 0:
            raise ValueError
    except ValueError:
        raise BadArgument("Template value must be a non-negative integer.")

    if filter_id not in filter_list[list_type].filters:
        raise BadArgument(
            f"Could not find filter with ID `{filter_id}` in the {list_type.name} {filter_list.name} list."
        )
    filter_ = filter_list[list_type].filters[filter_id]

    if not isinstance(filter_, filter_type):
        raise BadArgument(
            f"The template filter name is {filter_.name!r}, but the target filter is {filter_type.name!r}"
        )
    return filter_.overrides
