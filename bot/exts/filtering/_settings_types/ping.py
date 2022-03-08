from functools import cache
from typing import Any

from discord import Guild

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry


class Ping(ActionEntry):
    """A setting entry which adds the appropriate pings to the alert."""

    name = "mentions"
    description = {
        "guild_pings": (
            "A list of role IDs/role names/user IDs/user names/here/everyone. "
            "If a mod-alert is generated for a filter triggered in a public channel, these will be pinged."
        ),
        "dm_pings": (
            "A list of role IDs/role names/user IDs/user names/here/everyone. "
            "If a mod-alert is generated for a filter triggered in DMs, these will be pinged."
        )
    }

    def __init__(self, entry_data: Any):
        super().__init__(entry_data)

        self.guild_pings = set(entry_data["guild_pings"]) if entry_data["guild_pings"] else set()
        self.dm_pings = set(entry_data["dm_pings"]) if entry_data["dm_pings"] else set()

    async def action(self, ctx: FilterContext) -> None:
        """Add the stored pings to the alert message content."""
        mentions = self.guild_pings if ctx.channel.guild else self.dm_pings
        new_content = " ".join([self._resolve_mention(mention, ctx.channel.guild) for mention in mentions])
        ctx.alert_content = f"{new_content} {ctx.alert_content}"

    def __or__(self, other: ActionEntry):
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        if not isinstance(other, Ping):
            return NotImplemented

        return Ping({
            "ping_type": self.guild_pings | other.guild_pings,
            "dm_ping_type": self.dm_pings | other.dm_pings
        })

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
