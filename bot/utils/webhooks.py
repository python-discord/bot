
import discord
from discord import Embed

from bot.log import get_logger
from bot.utils.messages import sub_clyde

log = get_logger(__name__)


async def send_webhook(
        webhook: discord.Webhook,
        content: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        embed: Embed | None = None,
        wait: bool | None = False
) -> discord.Message:
    """
    Send a message using the provided webhook.

    This uses sub_clyde() and tries for an HTTPException to ensure it doesn't crash.
    """
    try:
        return await webhook.send(
            content=content,
            username=sub_clyde(username),
            avatar_url=avatar_url,
            embed=embed,
            wait=wait,
        )
    except discord.HTTPException:
        log.exception("Failed to send a message to the webhook!")
