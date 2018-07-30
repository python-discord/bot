import logging
import re

from discord import Colour, Message
from discord.ext.commands import Bot

from bot.cogs.modlog import ModLog
from bot.constants import (
    Channels, Colours, DEBUG_MODE,
    Filter, Icons
)

log = logging.getLogger(__name__)

INVITE_RE = (
    r"(?:discord(?:[\.,]|dot)gg|"                     # Could be discord.gg/
    r"discord(?:[\.,]|dot)com(?:\/|slash)invite|"     # or discord.com/invite/
    r"discordapp(?:[\.,]|dot)com(?:\/|slash)invite|"  # or discordapp.com/invite/
    r"discord(?:[\.,]|dot)me|"                        # or discord.me
    r"discord(?:[\.,]|dot)io"                         # or discord.io.
    r")(?:[\/]|slash)"                                # / or 'slash'
    r"([a-zA-Z0-9]+)"                                 # the invite code itself
)

URL_RE = "(https?://[^\s]+)"
ZALGO_RE = r"[\u0300-\u036F\u0489]"


class Filtering:
    """
    Filtering out invites, blacklisting domains,
    and warning us of certain regular expressions
    """

    def __init__(self, bot: Bot):
        self.bot = bot

        self.filters = {
            "filter_zalgo": {
                "enabled": Filter.filter_zalgo,
                "function": self._has_zalgo,
                "type": "filter"
            },
            "filter_invites": {
                "enabled": Filter.filter_invites,
                "function": self._has_invites,
                "type": "filter"
            },
            "filter_domains": {
                "enabled": Filter.filter_domains,
                "function": self._has_urls,
                "type": "filter"
            },
            "watch_words": {
                "enabled": Filter.watch_words,
                "function": self._has_watchlist_words,
                "type": "watchlist"
            },
            "watch_tokens": {
                "enabled": Filter.watch_tokens,
                "function": self._has_watchlist_tokens,
                "type": "watchlist"
            },
        }

    @property
    def mod_log(self) -> ModLog:
        return self.bot.get_cog("ModLog")

    async def on_message(self, msg: Message):
        """
        Whenever a message is received,
        run it through our filters to see if it
        violates any of our rules, and then respond
        accordingly.
        """

        # Should we filter this message?
        role_whitelisted = False
        for role in msg.author.roles:
            if role.id in Filter.role_whitelist:
                role_whitelisted = True

        filter_message = (
            msg.channel.id not in Filter.channel_whitelist  # Channel not in whitelist
            and not role_whitelisted                        # Role not in whitelist
            and not msg.author.bot                          # Author not a bot
        )

        # If we're running the bot locally, ignore role whitelist and only listen to #dev-test
        if DEBUG_MODE:
            filter_message = not msg.author.bot and msg.channel.id == Channels.devtest

        # If none of the above, we can start filtering.
        if filter_message:
            for filter_name, _filter in self.filters.items():

                # Is this specific filter enabled in the config?
                if _filter["enabled"]:
                    triggered = await _filter["function"](msg.content)

                    if triggered:
                        message = (
                            f"The {filter_name} {_filter['type']} was triggered "
                            f"by **{msg.author.name}#{msg.author.discriminator}** in "
                            f"<#{msg.channel.id}> with the following message:\n\n"
                            f"{msg.content}"
                        )

                        log.debug(message)
                        log.debug(Channels.mod_alerts)

                        # Send pretty mod log embed to mod-alerts
                        await self.mod_log.send_log_message(
                            icon_url=Icons.filtering,
                            colour=Colour(Colours.soft_red),
                            title=f"{_filter['type'].title()} triggered!",
                            text=message,
                            thumbnail=msg.author.avatar_url_as(static_format="png"),
                            channel_id=Channels.mod_alerts,
                            ping_everyone=Filter.ping_everyone,
                        )

                        # If this is a filter (not a watchlist), we should delete the message.
                        if _filter["type"] == "filter":
                            await msg.delete()

                        break  # We don't want multiple filters to trigger

    @staticmethod
    async def _has_watchlist_words(text: str) -> bool:
        """
        Returns True if the text contains
        one of the regular expressions from the
        word_watchlist in our filter config.

        Only matches words with boundaries before
        and after the expression.
        """

        for expression in Filter.word_watchlist:
            if re.search(fr"\b{expression}\b", text.lower()):
                return True

        return False

    @staticmethod
    async def _has_watchlist_tokens(text: str) -> bool:
        """
        Returns True if the text contains
        one of the regular expressions from the
        token_watchlist in our filter config.

        This will match the expression even if it
        does not have boundaries before and after
        """

        for expression in Filter.token_watchlist:
            if re.search(fr"{expression}", text.lower()):
                return True

        return False

    @staticmethod
    async def _has_urls(text: str) -> bool:
        """
        Returns True if the text contains one of
        the blacklisted URLs from the config file.
        """

        if not re.search(URL_RE.lower(), text.lower()):
            return False

        for url in Filter.domain_blacklist:
            if url.lower() in text.lower():
                return True

        return False

    @staticmethod
    async def _has_zalgo(text: str) -> bool:
        """
        Returns True if the text contains zalgo characters.

        Zalgo range is \u0300 – \u036F and \u0489.
        """

        return bool(re.search(ZALGO_RE, text))

    @staticmethod
    async def _has_invites(text: str) -> bool:
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
