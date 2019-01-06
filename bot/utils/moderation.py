import logging
from typing import Union

from aiohttp import ClientError
from discord import Member, Object, User
from discord.ext.commands import Context

from bot.constants import Keys, URLs

log = logging.getLogger(__name__)

HEADERS = {"X-API-KEY": Keys.site_api}


async def post_infraction(
    ctx: Context, user: Union[Member, Object, User],
    type: str, reason: str, duration: str = None, hidden: bool = False
):

    payload = {
        "actor": ctx.message.author.id,
        "hidden": hidden,
        "reason": reason,
        "type": type,
        "user": user.id
    }
    if duration:
        payload['duration'] = duration

    try:
        response = await ctx.bot.api_client.post(
            'bot/infractions', json=payload
        )
    except ClientError:
        log.exception("There was an error adding an infraction.")
        await ctx.send(":x: There was an error adding the infraction.")
        return

    return response
