from typing import ClassVar, Union

from pydantic import validator

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ValidationEntry


class ChannelScope(ValidationEntry):
    """A setting entry which tells whether the filter was invoked in a whitelisted channel or category."""

    name: ClassVar[str] = "channel_scope"
    description: ClassVar[str] = {
        "disabled_channels": "A list of channel IDs or channel names. The filter will not trigger in these channels.",
        "disabled_categories": (
            "A list of category IDs or category names. The filter will not trigger in these categories."
        ),
        "enabled_channels": (
            "A list of channel IDs or channel names. "
            "The filter can trigger in these channels even if the category is disabled."
        )
    }

    disabled_channels: set[Union[str, int]]
    disabled_categories: set[Union[str, int]]
    enabled_channels: set[Union[str, int]]

    @validator("*", pre=True)
    @classmethod
    def init_if_sequence_none(cls, sequence: list[str]) -> list[str]:
        """Initialize an empty sequence if the value is None."""
        if sequence is None:
            return []
        return sequence

    @validator("*", each_item=True)
    @classmethod
    def maybe_cast_items(cls, channel_or_category: str) -> Union[str, int]:
        """Cast to int each value in each sequence if it is alphanumeric."""
        if channel_or_category.isdigit():
            return int(channel_or_category)
        return channel_or_category

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
