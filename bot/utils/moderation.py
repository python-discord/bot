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
    ctx: Context,
    user: Union[Member, Object, User],
    type: str,
    reason: str,
    expires_at: datetime = None,
    hidden: bool = False,
    active: bool = True,
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


async def already_has_active_infraction(ctx: Context, user: Union[Member, Object, User], type: str) -> bool:
    """Checks if a user already has an active infraction of the given type."""
    active_infractions = await ctx.bot.api_client.get(
        'bot/infractions',
        params={
            'active': 'true',
            'type': type,
            'user__id': str(user.id)
        }
    )
    if active_infractions:
        await ctx.send(
            f":x: According to my records, this user already has a {type} infraction. "
            f"See infraction **#{active_infractions[0]['id']}**."
        )
        return True
    else:
        return False
