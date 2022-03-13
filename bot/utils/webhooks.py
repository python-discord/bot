from typing import Optional

import disnake
from disnake import Embed

from bot.log import get_logger
from bot.utils.messages import sub_clyde

log = get_logger(__name__)


async def send_webhook(
        webhook: disnake.Webhook,
        content: Optional[str] = None,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
        embed: Optional[Embed] = None,
        wait: Optional[bool] = False
) -> disnake.Message:
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
    except disnake.HTTPException:
        log.exception("Failed to send a message to the webhook!")
