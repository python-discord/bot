import logging
from datetime import datetime
from typing import Optional, Union

from discord import Member, Object, User
from discord.ext.commands import Context

from bot.api import ResponseCodeError
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
) -> Optional[dict]:
    """Posts an infraction to the API."""
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
        response = await ctx.bot.api_client.post('bot/infractions', json=payload)
    except ResponseCodeError as exp:
        if exp.status == 400 and 'user' in exp.response_data:
            log.info(
                f"{ctx.author} tried to add a {type} infraction to `{user.id}`, "
                "but that user id was not found in the database."
            )
            await ctx.send(f":x: Cannot add infraction, the specified user is not known to the database.")
            return
        else:
            log.exception("An unexpected ResponseCodeError occurred while adding an infraction:")
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
