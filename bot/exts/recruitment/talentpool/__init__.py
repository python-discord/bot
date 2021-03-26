from bot.bot import Bot


def setup(bot: Bot) -> None:
    """Load the TalentPool cog."""
    from bot.exts.recruitment.talentpool._cog import TalentPool

    bot.add_cog(TalentPool(bot))
