import logging
import typing as t
from datetime import datetime

import discord
from discord.ext import commands
from discord.ext.commands import Context

from bot.api import ResponseCodeError

log = logging.getLogger(__name__)

MemberObject = t.Union[discord.Member, discord.User, discord.Object]
Infraction = t.Dict[str, t.Union[str, int, bool]]


def proxy_user(user_id: str) -> discord.Object:
    """Create a proxy user for the provided user_id for situations where a Member or User object cannot be resolved."""
    try:
        user_id = int(user_id)
    except ValueError:
        raise commands.BadArgument

    user = discord.Object(user_id)
    user.mention = user.id
    user.avatar_url_as = lambda static_format: None

    return user


async def post_infraction(
    ctx: Context,
    user: MemberObject,
    type: str,
    reason: str,
    expires_at: datetime = None,
    hidden: bool = False,
    active: bool = True,
) -> t.Optional[dict]:
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
        if exp.status == 400 and 'user' in exp.response_json:
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


async def already_has_active_infraction(ctx: Context, user: MemberObject, type: str) -> bool:
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
