from functools import cache
from typing import Any

from discord import Guild

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry
from bot.exts.filtering._utils import ROLE_LITERALS


class Ping(ActionEntry):
    """A setting entry which adds the appropriate pings to the alert."""

    name = "mentions"

    def __init__(self, entry_data: Any):
        super().__init__(entry_data)
        self.guild_mentions = set(entry_data["guild_pings"])
        self.dm_mentions = set(entry_data["dm_pings"])

    async def action(self, ctx: FilterContext) -> None:
        """Add the stored pings to the alert message content."""
        mentions = self.guild_mentions if ctx.channel.guild else self.dm_mentions
        new_content = " ".join([self._resolve_mention(mention, ctx.channel.guild) for mention in mentions])
        ctx.alert_content = f"{new_content} {ctx.alert_content}"

    def __or__(self, other: ActionEntry):
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        if not isinstance(other, Ping):
            return NotImplemented

        return Ping({
            "ping_type": self.guild_mentions | other.guild_mentions,
            "dm_ping_type": self.dm_mentions | other.dm_mentions
        })

    @staticmethod
    @cache
    def _resolve_mention(mention: str, guild: Guild) -> str:
        """Return the appropriate formatting for the formatting, be it a literal, a user ID, or a role ID."""
        if mention in ("here", "everyone"):
            return f"@{mention}"
        if mention in ROLE_LITERALS:
            return f"<@&{ROLE_LITERALS[mention]}>"
        if not mention.isdigit():
            return mention

        mention = int(mention)
        if any(mention == role.id for role in guild.roles):
            return f"<@&{mention}>"
        else:
            return f"<@{mention}>"
