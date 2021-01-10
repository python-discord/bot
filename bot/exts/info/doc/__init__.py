from bot.bot import Bot
from ._redis_cache import DocRedisCache

MAX_SIGNATURE_AMOUNT = 3
PRIORITY_PACKAGES = (
    "python",
)

doc_cache = DocRedisCache(namespace="Docs")


def setup(bot: Bot) -> None:
    """Load the Doc cog."""
    from ._cog import DocCog
    bot.add_cog(DocCog(bot))
