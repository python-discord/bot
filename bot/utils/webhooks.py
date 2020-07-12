import logging
from typing import Optional

import discord
from discord import Embed

from bot.utils.messages import sub_clyde

log = logging.getLogger(__name__)


async def send_webhook(
        webhook: discord.Webhook,
        content: Optional[str] = None,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
        embed: Optional[Embed] = None,
        wait: Optional[bool] = False
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
