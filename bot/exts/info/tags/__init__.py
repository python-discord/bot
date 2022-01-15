from bot.bot import Bot


def setup(bot: Bot) -> None:
    """Load the Tags cog."""
    # Defer import to reduce side effects from importing the codeblock package.
    from bot.exts.info.tags._cog import Tags
    bot.add_cog(Tags(bot))
