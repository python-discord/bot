from functools import cache
from typing import ClassVar

from discord import Guild
from pydantic import validator

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry


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

    @validator("*", pre=True)
    @classmethod
    def init_sequence_if_none(cls, pings: list[str] | None) -> list[str]:
        """Initialize an empty sequence if the value is None."""
        if pings is None:
            return []
        return pings

    async def action(self, ctx: FilterContext) -> None:
        """Add the stored pings to the alert message content."""
        mentions = self.guild_pings if ctx.channel.guild else self.dm_pings
        new_content = " ".join([self._resolve_mention(mention, ctx.channel.guild) for mention in mentions])
        ctx.alert_content = f"{new_content} {ctx.alert_content}"

    def __or__(self, other: ActionEntry):
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        if not isinstance(other, Ping):
            return NotImplemented

        return Ping(guild_pings=self.guild_pings | other.guild_pings, dm_pings=self.dm_pings | other.dm_pings)

    @staticmethod
    @cache
    def _resolve_mention(mention: str, guild: Guild) -> str:
        """Return the appropriate formatting for the formatting, be it a literal, a user ID, or a role ID."""
        if mention in ("here", "everyone"):
            return f"@{mention}"
        if mention.isdigit():  # It's an ID.
            mention = int(mention)
            if any(mention == role.id for role in guild.roles):
                return f"<@&{mention}>"
            else:
                return f"<@{mention}>"

        # It's a name
        for role in guild.roles:
            if role.name == mention:
                return role.mention
        for member in guild.members:
            if str(member) == mention:
                return member.mention
        return mention
