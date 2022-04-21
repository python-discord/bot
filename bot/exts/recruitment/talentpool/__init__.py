from bot.bot import Bot


async def setup(bot: Bot) -> None:
    """Load the TalentPool cog."""
    from bot.exts.recruitment.talentpool._cog import TalentPool

    await bot.add_cog(TalentPool(bot))
