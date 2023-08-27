from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord
from discord import Interaction, SelectOption
from discord.ext.commands import BadArgument

from bot.exts.filtering._filter_lists import FilterList, ListType
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._settings_types.settings_entry import SettingsEntry
from bot.exts.filtering._ui.filter import filter_overrides_for_ui
from bot.exts.filtering._ui.ui import (
    COMPONENT_TIMEOUT,
    CustomCallbackSelect,
    EditBaseView,
    MISSING,
    SETTINGS_DELIMITER,
    parse_value,
    populate_embed_from_dict,
)


def search_criteria_converter(
    filter_lists: dict,
    loaded_filters: dict,
    loaded_settings: dict,
    loaded_filter_settings: dict,
    filter_type: type[Filter] | None,
    input_data: str
) -> tuple[dict[str, Any], dict[str, Any], type[Filter]]:
    """Parse a string representing setting overrides, and validate the setting names."""
    if not input_data:
        return {}, {}, filter_type

    parsed = SETTINGS_DELIMITER.split(input_data)
    if not parsed:
        return {}, {}, filter_type

    try:
        settings = {setting: value for setting, value in [part.split("=", maxsplit=1) for part in parsed]}  # noqa: C416
    except ValueError:
        raise BadArgument("The settings provided are not in the correct format.")

    template = None
    if "--template" in settings:
        template = settings.pop("--template")

    filter_settings = {}
    for setting, _ in list(settings.items()):
        if setting in loaded_settings:  # It's a filter list setting
            type_ = loaded_settings[setting][2]
            try:
                settings[setting] = parse_value(settings[setting], type_)
            except (TypeError, ValueError) as e:
                raise BadArgument(e)
        elif "/" not in setting:
            raise BadArgument(f"{setting!r} is not a recognized setting.")
        else:  # It's a filter setting
            filter_name, filter_setting_name = setting.split("/", maxsplit=1)
            if not filter_type:
                if filter_name in loaded_filters:
                    filter_type = loaded_filters[filter_name]
                else:
                    raise BadArgument(f"There's no filter type named {filter_name!r}.")
            if filter_name.lower() != filter_type.name.lower():
                raise BadArgument(
                    f"A setting for a {filter_name!r} filter was provided, "
                    f"but the filter name is {filter_type.name!r}"
                )
            if filter_setting_name not in loaded_filter_settings[filter_type.name]:
                raise BadArgument(f"{setting!r} is not a recognized setting.")
            type_ = loaded_filter_settings[filter_type.name][filter_setting_name][2]
            try:
                filter_settings[filter_setting_name] = parse_value(settings.pop(setting), type_)
            except (TypeError, ValueError) as e:
                raise BadArgument(e)

    # Pull templates settings and apply them.
    if template is not None:
        try:
            t_settings, t_filter_settings, filter_type = template_settings(template, filter_lists, filter_type)
        except ValueError as e:
            raise BadArgument(str(e))
        else:
            # The specified settings go on top of the template
            settings = t_settings | settings
            filter_settings = t_filter_settings | filter_settings

    return settings, filter_settings, filter_type


def get_filter(filter_id: int, filter_lists: dict) -> tuple[Filter, FilterList, ListType] | None:
    """Return a filter with the specific filter_id, if found."""
    for filter_list in filter_lists.values():
        for list_type, sublist in filter_list.items():
            if filter_id in sublist.filters:
                return sublist.filters[filter_id], filter_list, list_type
    return None


def template_settings(
    filter_id: str, filter_lists: dict, filter_type: type[Filter] | None
) -> tuple[dict, dict, type[Filter]]:
    """Find a filter with the specified ID and filter type, and return its settings and (maybe newly found) type."""
    try:
        filter_id = int(filter_id)
        if filter_id < 0:
            raise ValueError
    except ValueError:
        raise BadArgument("Template value must be a non-negative integer.")

    result = get_filter(filter_id, filter_lists)
    if not result:
        raise BadArgument(f"Could not find a filter with ID `{filter_id}`.")
    filter_, filter_list, list_type = result

    if filter_type and not isinstance(filter_, filter_type):
        raise BadArgument(f"The filter with ID `{filter_id}` is not of type {filter_type.name!r}.")

    settings, filter_settings = filter_overrides_for_ui(filter_)
    return settings, filter_settings, type(filter_)


def build_search_repr_dict(
    settings: dict[str, Any], filter_settings: dict[str, Any], filter_type: type[Filter] | None
) -> dict:
    """Build a dictionary of field names and values to pass to `populate_embed_from_dict`."""
    total_values = settings.copy()
    if filter_type:
        for setting_name, value in filter_settings.items():
            total_values[f"{filter_type.name}/{setting_name}"] = value

    return total_values


class SearchEditView(EditBaseView):
    """A view used to edit the search criteria before performing the search."""

    class _REMOVE:
        """Sentinel value for when an override should be removed."""

    def __init__(
        self,
        filter_type: type[Filter] | None,
        settings: dict[str, Any],
        filter_settings: dict[str, Any],
        loaded_filter_lists: dict[str, FilterList],
        loaded_filters: dict[str, type[Filter]],
        loaded_settings: dict[str, tuple[str, SettingsEntry, type]],
        loaded_filter_settings: dict[str, dict[str, tuple[str, SettingsEntry, type]]],
        author: discord.User | discord.Member,
        embed: discord.Embed,
        confirm_callback: Callable
    ):
        super().__init__(author)
        self.filter_type = filter_type
        self.settings = settings
        self.filter_settings = filter_settings
        self.loaded_filter_lists = loaded_filter_lists
        self.loaded_filters = loaded_filters
        self.loaded_settings = loaded_settings
        self.loaded_filter_settings = loaded_filter_settings
        self.embed = embed
        self.confirm_callback = confirm_callback

        title = "Filters Search"
        if filter_type:
            title += f" - {filter_type.name.title()}"
        embed.set_author(name=title)

        settings_repr_dict = build_search_repr_dict(settings, filter_settings, filter_type)
        populate_embed_from_dict(embed, settings_repr_dict)

        self.type_per_setting_name = {setting: info[2] for setting, info in loaded_settings.items()}
        if filter_type:
            self.type_per_setting_name.update({
                f"{filter_type.name}/{name}": type_
                for name, (_, _, type_) in loaded_filter_settings.get(filter_type.name, {}).items()
            })

        add_select = CustomCallbackSelect(
            self._prompt_new_value,
            placeholder="Add or edit criterion",
            options=[SelectOption(label=name) for name in sorted(self.type_per_setting_name)],
            row=0
        )
        self.add_item(add_select)

        if settings_repr_dict:
            remove_select = CustomCallbackSelect(
                self._remove_criterion,
                placeholder="Select a criterion to remove",
                options=[SelectOption(label=name) for name in sorted(settings_repr_dict)],
                row=1
            )
            self.add_item(remove_select)

    @discord.ui.button(label="Template", row=2)
    async def enter_template(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """A button to enter a filter template ID and copy its overrides over."""
        modal = TemplateModal(self, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Filter Type", row=2)
    async def enter_filter_type(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """A button to enter a filter type."""
        modal = FilterTypeModal(self, interaction.message)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green, row=3)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Confirm the search criteria and perform the search."""
        await interaction.response.edit_message(view=None)  # Make sure the interaction succeeds first.
        try:
            await self.confirm_callback(interaction.message, self.filter_type, self.settings, self.filter_settings)
        except BadArgument as e:
            await interaction.message.reply(
                embed=discord.Embed(colour=discord.Colour.red(), title="Bad Argument", description=str(e))
            )
            await interaction.message.edit(view=self)
        else:
            self.stop()

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.red, row=3)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the operation."""
        await interaction.response.edit_message(content="🚫 Operation canceled.", embed=None, view=None)
        self.stop()

    def current_value(self, setting_name: str) -> Any:
        """Get the current value stored for the setting or MISSING if none found."""
        if setting_name in self.settings:
            return self.settings[setting_name]
        if "/" in setting_name:
            _, setting_name = setting_name.split("/", maxsplit=1)
            if setting_name in self.filter_settings:
                return self.filter_settings[setting_name]
        return MISSING

    async def update_embed(
        self,
        interaction_or_msg: discord.Interaction | discord.Message,
        *,
        setting_name: str | None = None,
        setting_value: str | type[SearchEditView._REMOVE] | None = None,
    ) -> None:
        """
        Update the embed with the new information.

        If a setting name is provided with a _REMOVE value, remove the override.
        If `interaction_or_msg` is a Message, the invoking Interaction must be deferred before calling this function.
        """
        if not setting_name:  # Can be None just to make the function signature compatible with the parent class.
            return

        if "/" in setting_name:
            filter_name, setting_name = setting_name.split("/", maxsplit=1)
            dict_to_edit = self.filter_settings
        else:
            dict_to_edit = self.settings

        # Update the criterion value or remove it
        if setting_value is not self._REMOVE:
            dict_to_edit[setting_name] = setting_value
        elif setting_name in dict_to_edit:
            dict_to_edit.pop(setting_name)

        self.embed.clear_fields()
        new_view = self.copy()

        try:
            if isinstance(interaction_or_msg, discord.Interaction):
                await interaction_or_msg.response.edit_message(embed=self.embed, view=new_view)
            else:
                await interaction_or_msg.edit(embed=self.embed, view=new_view)
        except discord.errors.HTTPException:  # Just in case of faulty input.
            pass
        else:
            self.stop()

    async def _remove_criterion(self, interaction: Interaction, select: discord.ui.Select) -> None:
        """
        Remove the criterion the user selected, and edit the embed.

        The interaction needs to be the selection of the setting attached to the embed.
        """
        await self.update_embed(interaction, setting_name=select.values[0], setting_value=self._REMOVE)

    async def apply_template(self, template_id: str, embed_message: discord.Message, interaction: Interaction) -> None:
        """Set any unset criteria with settings values from the given filter."""
        try:
            settings, filter_settings, self.filter_type = template_settings(
                template_id, self.loaded_filter_lists, self.filter_type
            )
        except BadArgument as e:  # The interaction object is necessary to send an ephemeral message.
            await interaction.response.send_message(f":x: {e}", ephemeral=True)
            return
        else:
            await interaction.response.defer()

        self.settings = settings | self.settings
        self.filter_settings = filter_settings | self.filter_settings
        self.embed.clear_fields()
        await embed_message.edit(embed=self.embed, view=self.copy())
        self.stop()

    async def apply_filter_type(self, type_name: str, embed_message: discord.Message, interaction: Interaction) -> None:
        """Set a new filter type and reset any criteria for settings of the old filter type."""
        if type_name.lower() not in self.loaded_filters:
            if type_name.lower()[:-1] not in self.loaded_filters:  # In case the user entered the plural form.
                await interaction.response.send_message(f":x: No such filter type {type_name!r}.", ephemeral=True)
                return
            type_name = type_name[:-1]
        type_name = type_name.lower()
        await interaction.response.defer()

        if self.filter_type and type_name == self.filter_type.name:
            return
        self.filter_type = self.loaded_filters[type_name]
        self.filter_settings = {}
        self.embed.clear_fields()
        await embed_message.edit(embed=self.embed, view=self.copy())
        self.stop()

    def copy(self) -> SearchEditView:
        """Create a copy of this view."""
        return SearchEditView(
            self.filter_type,
            self.settings,
            self.filter_settings,
            self.loaded_filter_lists,
            self.loaded_filters,
            self.loaded_settings,
            self.loaded_filter_settings,
            self.author,
            self.embed,
            self.confirm_callback
        )


class TemplateModal(discord.ui.Modal, title="Template"):
    """A modal to enter a filter ID to copy its overrides over."""

    template = discord.ui.TextInput(label="Template Filter ID", required=False)

    def __init__(self, embed_view: SearchEditView, message: discord.Message):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.embed_view = embed_view
        self.message = message

    async def on_submit(self, interaction: Interaction) -> None:
        """Update the embed with the new description."""
        await self.embed_view.apply_template(self.template.value, self.message, interaction)


class FilterTypeModal(discord.ui.Modal, title="Template"):
    """A modal to enter a filter ID to copy its overrides over."""

    filter_type = discord.ui.TextInput(label="Filter Type")

    def __init__(self, embed_view: SearchEditView, message: discord.Message):
        super().__init__(timeout=COMPONENT_TIMEOUT)
        self.embed_view = embed_view
        self.message = message

    async def on_submit(self, interaction: Interaction) -> None:
        """Update the embed with the new description."""
        await self.embed_view.apply_filter_type(self.filter_type.value, self.message, interaction)
