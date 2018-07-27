import logging
import re

from discord import Message
from discord.ext.commands import Bot

from bot.constants import Channels

log = logging.getLogger(__name__)


class Filtering:
    """
    Filtering out invites, blacklisting domains,
    and preventing certain expressions"""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def on_message(self, msg: Message):

        has_zalgo = await self._filter_zalgo(msg.content)

        if has_zalgo:
            self.bot.get_channel(Channels.modlog).send(
                content="ZALGO!"
            )

    @staticmethod
    async def _has_zalgo(text):
        """
        Returns True if the text contains zalgo characters.

        Zalgo range is \u0300 – \u036F and \u0489.
        """

        return bool(re.search(r"[\u0300-\u036F\u0489]", text))


def setup(bot: Bot):
    bot.add_cog(Filtering(bot))
    log.info("Cog loaded: Filtering")
