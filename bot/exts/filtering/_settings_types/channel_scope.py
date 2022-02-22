from typing import Any, Union

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ValidationEntry


def maybe_cast_to_int(item: str) -> Union[str, int]:
    """Cast the item to int if it consists of only digit, or leave as is otherwise."""
    if item.isdigit():
        return int(item)
    return item


class ChannelScope(ValidationEntry):
    """A setting entry which tells whether the filter was invoked in a whitelisted channel or category."""

    name = "channel_scope"

    def __init__(self, entry_data: Any):
        super().__init__(entry_data)
        if entry_data["disabled_channels"]:
            self.disabled_channels = set(map(maybe_cast_to_int, entry_data["disabled_channels"]))
        else:
            self.disabled_channels = set()

        if entry_data["disabled_categories"]:
            self.disabled_categories = set(map(maybe_cast_to_int, entry_data["disabled_categories"]))
        else:
            self.disabled_categories = set()

        if entry_data["enabled_channels"]:
            self.enabled_channels = set(map(maybe_cast_to_int, entry_data["enabled_channels"]))
        else:
            self.enabled_channels = set()

    def triggers_on(self, ctx: FilterContext) -> bool:
        """
        Return whether the filter should be triggered in the given channel.

        The filter is invoked by default.
        If the channel is explicitly enabled, it bypasses the set disabled channels and categories.
        """
        channel = ctx.channel
        enabled_id = (
            channel.id in self.enabled_channels
            or (
                channel.id not in self.disabled_channels
                and (not channel.category or channel.category.id not in self.disabled_categories)
            )
        )
        enabled_name = (
            channel.name in self.enabled_channels
            or (
                channel.name not in self.disabled_channels
                and (not channel.category or channel.category.name not in self.disabled_categories)
            )
        )
        return enabled_id and enabled_name
