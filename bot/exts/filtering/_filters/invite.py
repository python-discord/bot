from botcore.utils.regex import DISCORD_INVITE
from discord import NotFound

import bot
from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter


class InviteFilter(Filter):
    """
    A filter which looks for invites to a specific guild in messages.

    The filter stores the guild ID which is allowed or denied.
    """

    name = "invite"

    def __init__(self, filter_data: dict):
        super().__init__(filter_data)
        self.content = int(self.content)

    def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a guild ID in the context content, given as a set of IDs."""
        return self.content in ctx.content

    @classmethod
    async def process_content(cls, content: str) -> str:
        """
        Process the content into a form which will work with the filtering.

        A ValueError should be raised if the content can't be used.
        """
        match = DISCORD_INVITE.fullmatch(content)
        if not match or not match.group("invite"):
            raise ValueError(f"`{content}` is not a valid Discord invite.")
        invite_code = match.group("invite")
        try:
            invite = await bot.instance.fetch_invite(invite_code)
        except NotFound:
            raise ValueError(f"`{invite_code}` is not a valid Discord invite code.")
        if not invite.guild:
            raise ValueError("Did you just try to add a group DM?")
        return str(invite.guild.id)
