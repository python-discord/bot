# coding=utf-8
import logging

from discord.ext.commands import AutoShardedBot, Context

log = logging.getLogger(__name__)


class Security:
    """
    Security-related helpers
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.bot.check(self.check_not_bot)  # Global commands check - no bots can run any commands at all

    def check_not_bot(self, ctx: Context):
        return not ctx.author.bot


def setup(bot):
    bot.add_cog(Security(bot))
    log.info("Cog loaded: Security")
