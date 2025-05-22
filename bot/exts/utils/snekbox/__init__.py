from bot.bot import Bot
from bot.exts.utils.snekbox._cog import CodeblockConverter, Snekbox, SupportedPythonVersions
from bot.exts.utils.snekbox._eval import EvalJob, EvalResult

__all__ = ("CodeblockConverter", "EvalJob", "EvalResult", "Snekbox", "SupportedPythonVersions")


async def setup(bot: Bot) -> None:
    """Load the Snekbox cog."""
    # Defer import to reduce side effects from importing the codeblock package.
    from bot.exts.utils.snekbox._cog import Snekbox
    await bot.add_cog(Snekbox(bot))
