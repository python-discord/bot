import re

from discord import NotFound
from discord.ext.commands import BadArgument
from pydis_core.utils.regex import DISCORD_INVITE

import bot
from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter


class InviteFilter(Filter):
    """
    A filter which looks for invites to a specific guild in messages.

    The filter stores the guild ID which is allowed or denied.
    """

    name = "invite"

    def __init__(self, filter_data: dict, defaults_data: dict | None = None):
        super().__init__(filter_data, defaults_data)
        self.content = int(self.content)

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a guild ID in the context content, given as a set of IDs."""
        return self.content in ctx.content

    @classmethod
    async def process_input(cls, content: str, description: str) -> tuple[str, str]:
        """
        Process the content and description into a form which will work with the filtering.

        A BadArgument should be raised if the content can't be used.
        """
        match = DISCORD_INVITE.fullmatch(content)
        if not match or not match.group("invite"):
            if not re.fullmatch(r"\S+", content):
                raise BadArgument(f"`{content}` is not a valid Discord invite.")
            invite_code = content
        else:
            invite_code = match.group("invite")

        try:
            invite = await bot.instance.fetch_invite(invite_code)
        except NotFound:
            raise BadArgument(f"`{invite_code}` is not a valid Discord invite code.")
        if not invite.guild:
            raise BadArgument("Did you just try to add a group DM?")

        guild_name = invite.guild.name if hasattr(invite.guild, "name") else ""
        if guild_name.lower() not in description.lower():
            description = " - ".join(part for part in (f'Guild "{guild_name}"', description) if part)
        return str(invite.guild.id), description
