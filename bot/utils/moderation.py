import logging
from typing import Union

from aiohttp import ClientError
from discord import Member, Object, User
from discord.ext.commands import Context

from bot.constants import Keys, URLs

log = logging.getLogger(__name__)

HEADERS = {"X-API-KEY": Keys.site_api}


async def post_infraction(
    ctx: Context, user: Union[Member, Object, User], type: str, reason: str, duration: str = None, hidden: bool = False
):
    try:
        response = await ctx.bot.http_session.post(
            URLs.site_infractions,
            headers=HEADERS,
            json={
                "type": type,
                "reason": reason,
                "duration": duration,
                "user_id": str(user.id),
                "actor_id": str(ctx.message.author.id),
                "hidden": hidden,
            },
        )
    except ClientError:
        log.exception("There was an error adding an infraction.")
        await ctx.send(":x: There was an error adding the infraction.")
        return

    response_object = await response.json()
    if "error_code" in response_object:
        await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
        return

    return response_object
