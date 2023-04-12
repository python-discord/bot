from typing import ClassVar, Union

from pydantic import validator

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ValidationEntry


class ChannelScope(ValidationEntry):
    """A setting entry which tells whether the filter was invoked in a whitelisted channel or category."""

    name: ClassVar[str] = "channel_scope"
    description: ClassVar[dict[str, str]] = {
        "disabled_channels": (
            "A list of channel IDs or channel names. "
            "The filter will not trigger in these channels even if the category is expressly enabled."
        ),
        "disabled_categories": (
            "A list of category IDs or category names. The filter will not trigger in these categories."
        ),
        "enabled_channels": (
            "A list of channel IDs or channel names. "
            "The filter can trigger in these channels even if the category is disabled or not expressly enabled."
        ),
        "enabled_categories": (
            "A list of category IDs or category names. "
            "If the list is not empty, filters will trigger only in channels of these categories, "
            "unless the channel is expressly disabled."
        )
    }

    # NOTE: Don't change this to use the new 3.10 union syntax unless you ensure Pydantic type validation and coercion
    # work properly. At the time of writing this code there's a difference.
    disabled_channels: set[Union[int, str]]  # noqa: UP007
    disabled_categories: set[Union[int, str]]  # noqa: UP007
    enabled_channels: set[Union[int, str]]  # noqa: UP007
    enabled_categories: set[Union[int, str]]  # noqa: UP007

    @validator("*", pre=True)
    @classmethod
    def init_if_sequence_none(cls, sequence: list[str] | None) -> list[str]:
        """Initialize an empty sequence if the value is None."""
        if sequence is None:
            return []
        return sequence

    def triggers_on(self, ctx: FilterContext) -> bool:
        """
        Return whether the filter should be triggered in the given channel.

        The filter is invoked by default.
        If the channel is explicitly enabled, it bypasses the set disabled channels and categories.
        """
        channel = ctx.channel

        if not channel:
            return True
        if not ctx.in_guild:  # This is not a guild channel, outside the scope of this setting.
            return True
        if hasattr(channel, "parent"):
            channel = channel.parent

        enabled_channel = channel.id in self.enabled_channels or channel.name in self.enabled_channels
        disabled_channel = channel.id in self.disabled_channels or channel.name in self.disabled_channels
        enabled_category = channel.category and (not self.enabled_categories or (
                channel.category.id in self.enabled_categories or channel.category.name in self.enabled_categories
        ))
        disabled_category = channel.category and (
            channel.category.id in self.disabled_categories or channel.category.name in self.disabled_categories
        )

        return enabled_channel or (enabled_category and not disabled_channel and not disabled_category)
