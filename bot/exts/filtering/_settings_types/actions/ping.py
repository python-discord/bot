from typing import ClassVar, Self

from pydantic import field_validator

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry
from bot.exts.filtering._utils import resolve_mention


class Ping(ActionEntry):
    """A setting entry which adds the appropriate pings to the alert."""

    name: ClassVar[str] = "mentions"
    description: ClassVar[dict[str, str]] = {
        "guild_pings": (
            "A list of role IDs/role names/user IDs/user names/here/everyone. "
            "If a mod-alert is generated for a filter triggered in a public channel, these will be pinged."
        ),
        "dm_pings": (
            "A list of role IDs/role names/user IDs/user names/here/everyone. "
            "If a mod-alert is generated for a filter triggered in DMs, these will be pinged."
        )
    }

    guild_pings: set[str]
    dm_pings: set[str]

    @field_validator("*", mode="before")
    @classmethod
    def init_sequence_if_none(cls, pings: list[str] | None) -> list[str]:
        """Initialize an empty sequence if the value is None."""
        if pings is None:
            return []
        return pings

    async def action(self, ctx: FilterContext) -> None:
        """Add the stored pings to the alert message content."""
        mentions = self.guild_pings if not ctx.channel or ctx.channel.guild else self.dm_pings
        new_content = " ".join([resolve_mention(mention) for mention in mentions])
        ctx.alert_content = f"{new_content} {ctx.alert_content}"

    def union(self, other: Self) -> Self:
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        return Ping(guild_pings=self.guild_pings | other.guild_pings, dm_pings=self.dm_pings | other.dm_pings)
