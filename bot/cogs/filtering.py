import logging
import re

from discord import Message
from discord.ext.commands import Bot

log = logging.getLogger(__name__)


class Filtering:
    """
    Filtering out invites, blacklisting domains,
    and preventing certain expressions"""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def on_message(self, msg: Message):
        self._filter_zalgo(msg.content)

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
