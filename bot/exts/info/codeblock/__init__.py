from bot.bot import Bot


async def setup(bot: Bot) -> None:
    """Load the CodeBlockCog cog."""
    # Defer import to reduce side effects from importing the codeblock package.
    from bot.exts.info.codeblock._cog import CodeBlockCog
    await bot.add_cog(CodeBlockCog(bot))
