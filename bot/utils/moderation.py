import logging
from datetime import datetime
from typing import Union

from aiohttp import ClientError
from discord import Member, Object, User
from discord.ext.commands import Context

from bot.constants import Keys

log = logging.getLogger(__name__)

HEADERS = {"X-API-KEY": Keys.site_api}


async def post_infraction(
    ctx: Context, user: Union[Member, Object, User], type: str, reason: str,
    expires_at: datetime = None, hidden: bool = False, active: bool = True
):

    payload = {
        "actor": ctx.message.author.id,
        "hidden": hidden,
        "reason": reason,
        "type": type,
        "user": user.id,
        "active": active
    }
    if expires_at:
        payload['expires_at'] = expires_at.isoformat()

    try:
        response = await ctx.bot.api_client.post(
            'bot/infractions', json=payload
        )
    except ClientError:
        log.exception("There was an error adding an infraction.")
        await ctx.send(":x: There was an error adding the infraction.")
        return

    return response
