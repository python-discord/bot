import discord

import bot
from bot.log import get_logger

log = get_logger(__name__)


async def get_or_fetch_user(user_id: int) -> discord.User:
    """Get a user from the cache or fetch the user if needed."""
    log.trace(f"Getting the user {user_id}.")

    user = bot.instance.get_user(user_id)
    if not user:
        log.debug(f"User {user_id} is not in cache; fetching from API.")
        user = await bot.instance.fetch_user(user_id)

    log.trace(f"User {user} ({user.id}) retrieved.")
    return user
