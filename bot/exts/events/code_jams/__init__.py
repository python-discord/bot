from bot.bot import Bot


def setup(bot: Bot) -> None:
    """Load the CodeJams cog."""
    from bot.exts.events.code_jams._cog import CodeJams

    bot.add_cog(CodeJams(bot))
