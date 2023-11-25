from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord
from discord import Embed, Interaction, SelectOption, User
from discord.ext.commands import BadArgument
from pydis_core.site_api import ResponseCodeError

from bot.exts.filtering._filter_lists import FilterList, ListType
from bot.exts.filtering._ui.ui import (
    CustomCallbackSelect,
    EditBaseView,
    MISSING,
    SETTINGS_DELIMITER,
    format_response_error,
    parse_value,
    populate_embed_from_dict,
)
from bot.exts.filtering._utils import repr_equals, to_serializable


def settings_converter(loaded_settings: dict, input_data: str) -> dict[str, Any]:
    """Parse a string representing settings, and validate the setting names."""
    if not input_data:
        return {}

    parsed = SETTINGS_DELIMITER.split(input_data)
    if not parsed:
        return {}

    try:
        settings = {setting: value for setting, value in [part.split("=", maxsplit=1) for part in parsed]}  # noqa: C416
    except ValueError:
        raise BadArgument("The settings provided are not in the correct format.")

    for setting in settings:
        if setting not in loaded_settings:
            raise BadArgument(f"{setting!r} is not a recognized setting.")

        type_ = loaded_settings[setting][2]
        try:
            parsed_value = parse_value(settings.pop(setting), type_)
            settings[setting] = parsed_value
        except (TypeError, ValueError) as e:
            raise BadArgument(e)

    return settings


def build_filterlist_repr_dict(filter_list: FilterList, list_type: ListType, new_settings: dict) -> dict:
    """Build a dictionary of field names and values to pass to `_build_embed_from_dict`."""
    # Get filter list settings
    default_setting_values = {}
    for settings_group in filter_list[list_type].defaults:
        for _, setting in settings_group.items():
            default_setting_values.update(to_serializable(setting.model_dump(), ui_repr=True))

    # Add new values. It's done in this way to preserve field order, since the new_values won't have all settings.
    total_values = {}
    for name, value in default_setting_values.items():
        if name not in new_settings or repr_equals(new_settings[name], value):
            total_values[name] = value
        else:
            total_values[f"{name}~"] = new_settings[name]

    return total_values


class FilterListAddView(EditBaseView):
    """A view used to add a new filter list."""

    def __init__(
        self,
        list_name: str,
        list_type: ListType,
        settings: dict,
        loaded_settings: dict,
        author: User,
        embed: Embed,
        confirm_callback: Callable
    ):
        super().__init__(author)
        self.list_name = list_name
        self.list_type = list_type
        self.settings = settings
        self.loaded_settings = loaded_settings
        self.embed = embed
        self.confirm_callback = confirm_callback

        self.settings_repr_dict = {name: to_serializable(value) for name, value in settings.items()}
        populate_embed_from_dict(embed, self.settings_repr_dict)

        self.type_per_setting_name = {setting: info[2] for setting, info in loaded_settings.items()}

        edit_select = CustomCallbackSelect(
            self._prompt_new_value,
            placeholder="Select a setting to edit",
            options=[SelectOption(label=name) for name in sorted(settings)],
            row=0
        )
        self.add_item(edit_select)

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green, row=1)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Confirm the content, description, and settings, and update the filters database."""
        await interaction.response.edit_message(view=None)  # Make sure the interaction succeeds first.
        try:
            await self.confirm_callback(interaction.message, self.list_name, self.list_type, self.settings)
        except ResponseCodeError as e:
            await interaction.message.reply(embed=format_response_error(e))
            await interaction.message.edit(view=self)
        else:
            self.stop()

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.red, row=1)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the operation."""
        await interaction.response.edit_message(content="🚫 Operation canceled.", embed=None, view=None)
        self.stop()

    def current_value(self, setting_name: str) -> Any:
        """Get the current value stored for the setting or MISSING if none found."""
        if setting_name in self.settings:
            return self.settings[setting_name]
        return MISSING

    async def update_embed(
        self,
        interaction_or_msg: discord.Interaction | discord.Message,
        *,
        setting_name: str | None = None,
        setting_value: str | None = None,
    ) -> None:
        """
        Update the embed with the new information.

        If `interaction_or_msg` is a Message, the invoking Interaction must be deferred before calling this function.
        """
        if not setting_name:  # Obligatory check to match the signature in the parent class.
            return

        self.settings[setting_name] = setting_value

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

    def copy(self) -> FilterListAddView:
        """Create a copy of this view."""
        return FilterListAddView(
            self.list_name,
            self.list_type,
            self.settings,
            self.loaded_settings,
            self.author,
            self.embed,
            self.confirm_callback
        )


class FilterListEditView(EditBaseView):
    """A view used to edit a filter list's settings before updating the database."""

    def __init__(
        self,
        filter_list: FilterList,
        list_type: ListType,
        new_settings: dict,
        loaded_settings: dict,
        author: User,
        embed: Embed,
        confirm_callback: Callable
    ):
        super().__init__(author)
        self.filter_list = filter_list
        self.list_type = list_type
        self.settings = new_settings
        self.loaded_settings = loaded_settings
        self.embed = embed
        self.confirm_callback = confirm_callback

        self.settings_repr_dict = build_filterlist_repr_dict(filter_list, list_type, new_settings)
        populate_embed_from_dict(embed, self.settings_repr_dict)

        self.type_per_setting_name = {setting: info[2] for setting, info in loaded_settings.items()}

        edit_select = CustomCallbackSelect(
            self._prompt_new_value,
            placeholder="Select a setting to edit",
            options=[SelectOption(label=name) for name in sorted(self.type_per_setting_name)],
            row=0
        )
        self.add_item(edit_select)

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green, row=1)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Confirm the content, description, and settings, and update the filters database."""
        await interaction.response.edit_message(view=None)  # Make sure the interaction succeeds first.
        try:
            await self.confirm_callback(interaction.message, self.filter_list, self.list_type, self.settings)
        except ResponseCodeError as e:
            await interaction.message.reply(embed=format_response_error(e))
            await interaction.message.edit(view=self)
        else:
            self.stop()

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.red, row=1)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the operation."""
        await interaction.response.edit_message(content="🚫 Operation canceled.", embed=None, view=None)
        self.stop()

    def current_value(self, setting_name: str) -> Any:
        """Get the current value stored for the setting or MISSING if none found."""
        if setting_name in self.settings:
            return self.settings[setting_name]
        if setting_name in self.settings_repr_dict:
            return self.settings_repr_dict[setting_name]
        return MISSING

    async def update_embed(
        self,
        interaction_or_msg: discord.Interaction | discord.Message,
        *,
        setting_name: str | None = None,
        setting_value: str | None = None,
    ) -> None:
        """
        Update the embed with the new information.

        If `interaction_or_msg` is a Message, the invoking Interaction must be deferred before calling this function.
        """
        if not setting_name:  # Obligatory check to match the signature in the parent class.
            return

        default_value = self.filter_list[self.list_type].default(setting_name)
        if not repr_equals(setting_value, default_value):
            self.settings[setting_name] = setting_value
        # If there's already a new value, remove it, since the new value is the same as the default.
        elif setting_name in self.settings:
            self.settings.pop(setting_name)

        self.embed.clear_fields()
        new_view = self.copy()

        try:
            if isinstance(interaction_or_msg, discord.Interaction):
                await interaction_or_msg.response.edit_message(embed=self.embed, view=new_view)
            else:
                await interaction_or_msg.edit(embed=self.embed, view=new_view)
        except discord.errors.HTTPException:  # Various errors such as embed description being too long.
            pass
        else:
            self.stop()

    def copy(self) -> FilterListEditView:
        """Create a copy of this view."""
        return FilterListEditView(
            self.filter_list,
            self.list_type,
            self.settings,
            self.loaded_settings,
            self.author,
            self.embed,
            self.confirm_callback
        )
