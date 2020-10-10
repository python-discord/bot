from discord.ext.commands import Cog

from bot.bot import Bot


class VoiceGate(Cog):
    """Voice channels verification management."""

    def __init__(self, bot: Bot):
        self.bot = bot


def setup(bot: Bot) -> None:
    """Loads the VoiceGate cog."""
    bot.add_cog(VoiceGate(bot))
