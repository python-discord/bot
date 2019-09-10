import logging

from discord.ext.commands import Bot, Context

log = logging.getLogger(__name__)


class Security:
    """Security-related helpers."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.bot.check(self.check_not_bot)  # Global commands check - no bots can run any commands at all
        self.bot.check(self.check_on_guild)  # Global commands check - commands can't be run in a DM

    def check_not_bot(self, ctx: Context) -> bool:
        """Check if Context instance author is not a bot."""
        return not ctx.author.bot

    def check_on_guild(self, ctx: Context) -> bool:
        """Check if Context instance has a guild attribute."""
        return ctx.guild is not None


def setup(bot: Bot) -> None:
    """Security cog load."""
    bot.add_cog(Security(bot))
    log.info("Cog loaded: Security")
