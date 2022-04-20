from bot.bot import Bot

from ._redis_cache import DocRedisCache

MAX_SIGNATURE_AMOUNT = 3
PRIORITY_PACKAGES = (
    "python",
)
NAMESPACE = "doc"

doc_cache = DocRedisCache(namespace=NAMESPACE)


async def setup(bot: Bot) -> None:
    """Load the Doc cog."""
    from ._cog import DocCog
    await bot.add_cog(DocCog(bot))
