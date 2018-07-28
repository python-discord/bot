import logging
import re

from discord import Message
from discord.ext.commands import Bot

from bot.constants import Channels, Filter

log = logging.getLogger(__name__)

INVITE_RE = (
    r"(?:discord(?:[\.,]|dot)gg|"                     # Could be discord.gg/
    r"discord(?:[\.,]|dot)com(?:\/|slash)invite|"     # or discord.com/invite/
    r"discordapp(?:[\.,]|dot)com(?:\/|slash)invite|"  # or discordapp.com/invite/
    r"discord(?:[\.,]|dot)me|"                        # or discord.me
    r"discord(?:[\.,]|dot)io"                         # or discord.io.
    r")(?:[\/]|slash)"                                # / or slash
    r"([a-zA-Z0-9]+)"                                 # the invite code itself
)

URL_RE = "(https?://[^\s]+)"
ZALGO_RE = r"[\u0300-\u036F\u0489]"


class Filtering:
    """
    Filtering out invites, blacklisting domains,
    and preventing certain expressions
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    async def on_message(self, msg: Message):

        if msg.channel.id == Channels.devtest and not msg.author.bot:

            has_zalgo = await self._has_zalgo(msg.content)
            has_invites = await self._has_invites(msg.content)
            has_urls = await self._has_urls(msg.content)

            if has_zalgo:
                await self.bot.get_channel(msg.channel.id).send(
                    content="ZALGO!"
                )

            if has_invites:
                await self.bot.get_channel(msg.channel.id).send(
                    content="INVITES!"
                )

            if has_urls:
                await self.bot.get_channel(msg.channel.id).send(
                    content="EVIL ILLEGAL HITLER DOMAINS!"
                )

    @staticmethod
    async def _has_urls(text):
        """
        Returns True if the text contains one of
        the blacklisted URLs from the config file.
        """

        if not re.search(URL_RE, text):
            return False

        for url in Filter.domain_blacklist:
            if url in text:
                return True

        return False

    @staticmethod
    async def _has_zalgo(text):
        """
        Returns True if the text contains zalgo characters.

        Zalgo range is \u0300 – \u036F and \u0489.
        """

        return bool(re.search(ZALGO_RE, text))

    @staticmethod
    async def _has_invites(text):
        """
        Returns True if the text contains an invite which
        is not on the guild_invite_whitelist in config.yml.

        Also catches a lot of common ways to try to cheat the system.
        """

        # Remove spaces to prevent cases like
        # d i s c o r d . c o m / i n v i t e / p y t h o n
        text = text.replace(" ", "")

        # Remove backslashes to prevent escape character aroundfuckery like
        # discord\.gg/gdudes-pony-farm
        text = text.replace("\\", "")

        invites = re.findall(INVITE_RE, text)
        for invite in invites:

            filter_invite = (
                invite not in Filter.guild_invite_whitelist
                and invite.lower() not in Filter.vanity_url_whitelist
            )

            if filter_invite:
                return True
        return False


def setup(bot: Bot):
    bot.add_cog(Filtering(bot))
    log.info("Cog loaded: Filtering")
