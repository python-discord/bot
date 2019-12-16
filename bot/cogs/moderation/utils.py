import logging
import textwrap
import typing as t
from datetime import datetime

import discord
from discord.ext import commands
from discord.ext.commands import Context

from bot.api import ResponseCodeError
from bot.constants import Colours, Icons
from bot.converters import Duration, FetchedUser, ISODateTime

log = logging.getLogger(__name__)

# apply icon, pardon icon
INFRACTION_ICONS = {
    "ban": (Icons.user_ban, Icons.user_unban),
    "kick": (Icons.sign_out, None),
    "mute": (Icons.user_mute, Icons.user_unmute),
    "note": (Icons.user_warn, None),
    "superstar": (Icons.superstarify, Icons.unsuperstarify),
    "warning": (Icons.user_warn, None),
}
RULES_URL = "https://pythondiscord.com/pages/rules"
APPEALABLE_INFRACTIONS = ("ban", "mute")

UserTypes = t.Union[discord.Member, discord.User, FetchedUser]
MemberObject = t.Union[UserTypes, discord.Object]
Infraction = t.Dict[str, t.Union[str, int, bool]]
Expiry = t.Union[Duration, ISODateTime]


async def post_user(ctx: Context, user: discord.User) -> t.Optional[dict]:
    """
    Create a new user in the database.

    Used when an infraction needs to be applied on a user absent in the guild.
    """
    log.warn("Attempting to add user to the database.")

    payload = {
        'avatar_hash': user.avatar,
        'discriminator': int(user.discriminator),
        'id': user.id,
        'in_guild': False,
        'name': user.name,
        'roles': []
    }

    try:
        response = await ctx.bot.api_client.post('bot/users', json=payload)
    except ResponseCodeError:
        # TODO: Add details, and specific information per possible situation.
        #  Potential race condition if someone joins and the bot syncs before the API replies!
        log.info("Couldn't post user.")
        # TODO: Rewrite message.
        await ctx.send("Tried to post user to the DB, couldn't be done.")

        return

    return response


# TODO: maybe delete proxy_user

def proxy_user(user_id: str) -> discord.Object:
    """
    Create a proxy user object from the given id.

    Used when a Member or User object cannot be resolved.
    """
    log.trace(f"Attempting to create a proxy user for the user id {user_id}.")

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
    infr_type: str,
    reason: str,
    expires_at: datetime = None,
    hidden: bool = False,
    active: bool = True
) -> t.Optional[dict]:
    """Posts an infraction to the API."""
    log.trace(f"Posting {infr_type} infraction for {user} to the API.")

    payload = {
        "actor": ctx.message.author.id,
        "hidden": hidden,
        "reason": reason,
        "type": infr_type,
        "user": user.id,
        "active": active
    }
    if expires_at:
        payload['expires_at'] = expires_at.isoformat()

    # Try to apply the infraction. If it fails because the user doesn't exist, try to add it.
    for attempt in range(2):
        try:
            response = await ctx.bot.api_client.post('bot/infractions', json=payload)
        except ResponseCodeError as exp:
            if exp.status == 400 and 'user'in exp.response_json:
                # Only once attempt to try to add the user to the database, not two:
                if attempt > 0 or await post_user(ctx, user) is None:
                    return
            else:
                log.exception("An unexpected ResponseCodeError occurred while adding an infraction:")
                await ctx.send(":x: There was an error adding the infraction.")
                return
        else:
            break

    return response


async def has_active_infraction(ctx: Context, user: MemberObject, infr_type: str) -> bool:
    """Checks if a user already has an active infraction of the given type."""
    log.trace(f"Checking if {user} has active infractions of type {infr_type}.")

    active_infractions = await ctx.bot.api_client.get(
        'bot/infractions',
        params={
            'active': 'true',
            'type': infr_type,
            'user__id': str(user.id)
        }
    )
    if active_infractions:
        log.trace(f"{user} has active infractions of type {infr_type}.")
        await ctx.send(
            f":x: According to my records, this user already has a {infr_type} infraction. "
            f"See infraction **#{active_infractions[0]['id']}**."
        )
        return True
    else:
        log.trace(f"{user} does not have active infractions of type {infr_type}.")
        return False


async def notify_infraction(
    user: UserTypes,
    infr_type: str,
    expires_at: t.Optional[str] = None,
    reason: t.Optional[str] = None,
    icon_url: str = Icons.token_removed
) -> bool:
    """DM a user about their new infraction and return True if the DM is successful."""
    log.trace(f"Sending {user} a DM about their {infr_type} infraction.")

    embed = discord.Embed(
        description=textwrap.dedent(f"""
            **Type:** {infr_type.capitalize()}
            **Expires:** {expires_at or "N/A"}
            **Reason:** {reason or "No reason provided."}
            """),
        colour=Colours.soft_red
    )

    embed.set_author(name="Infraction information", icon_url=icon_url, url=RULES_URL)
    embed.title = f"Please review our rules over at {RULES_URL}"
    embed.url = RULES_URL

    if infr_type in APPEALABLE_INFRACTIONS:
        embed.set_footer(
            text="To appeal this infraction, send an e-mail to appeals@pythondiscord.com"
        )

    return await send_private_embed(user, embed)


async def notify_pardon(
    user: UserTypes,
    title: str,
    content: str,
    icon_url: str = Icons.user_verified
) -> bool:
    """DM a user about their pardoned infraction and return True if the DM is successful."""
    log.trace(f"Sending {user} a DM about their pardoned infraction.")

    embed = discord.Embed(
        description=content,
        colour=Colours.soft_green
    )

    embed.set_author(name=title, icon_url=icon_url)

    return await send_private_embed(user, embed)


async def send_private_embed(user: UserTypes, embed: discord.Embed) -> bool:
    """
    A helper method for sending an embed to a user's DMs.

    Returns a boolean indicator of DM success.
    """
    try:
        await user.send(embed=embed)
        return True
    except (discord.HTTPException, discord.Forbidden, discord.NotFound):
        log.debug(
            f"Infraction-related information could not be sent to user {user} ({user.id}). "
            "The user either could not be retrieved or probably disabled their DMs."
        )
        return False
