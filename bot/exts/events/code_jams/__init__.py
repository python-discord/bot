from bot.bot import Bot


async def setup(bot: Bot) -> None:
    """Load the CodeJams cog."""
    from bot.exts.events.code_jams._cog import CodeJams

    await bot.add_cog(CodeJams(bot))
