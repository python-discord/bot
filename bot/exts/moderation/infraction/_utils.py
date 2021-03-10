import logging
import typing as t
from datetime import datetime

import discord
from discord.ext.commands import Context

from bot.api import ResponseCodeError
from bot.constants import Colours, Icons
from bot.errors import InvalidInfractedUser

log = logging.getLogger(__name__)

# apply icon, pardon icon
INFRACTION_ICONS = {
    "ban": (Icons.user_ban, Icons.user_unban),
    "kick": (Icons.sign_out, None),
    "mute": (Icons.user_mute, Icons.user_unmute),
    "note": (Icons.user_warn, None),
    "superstar": (Icons.superstarify, Icons.unsuperstarify),
    "warning": (Icons.user_warn, None),
    "voice_ban": (Icons.voice_state_red, Icons.voice_state_green),
}
RULES_URL = "https://pythondiscord.com/pages/rules"
APPEALABLE_INFRACTIONS = ("ban", "mute", "voice_ban")

# Type aliases
UserObject = t.Union[discord.Member, discord.User]
UserSnowflake = t.Union[UserObject, discord.Object]
Infraction = t.Dict[str, t.Union[str, int, bool]]

APPEAL_EMAIL = "appeals@pythondiscord.com"

INFRACTION_TITLE = f"Please review our rules over at {RULES_URL}"
INFRACTION_APPEAL_FOOTER = f"To appeal this infraction, send an e-mail to {APPEAL_EMAIL}"
INFRACTION_AUTHOR_NAME = "Infraction information"

INFRACTION_DESCRIPTION_TEMPLATE = (
    "**Type:** {type}\n"
    "**Expires:** {expires}\n"
    "**Reason:** {reason}\n"
)


async def post_user(ctx: Context, user: UserSnowflake) -> t.Optional[dict]:
    """
    Create a new user in the database.

    Used when an infraction needs to be applied on a user absent in the guild.
    """
    log.trace(f"Attempting to add user {user.id} to the database.")

    if not isinstance(user, (discord.Member, discord.User)):
        log.debug("The user being added to the DB is not a Member or User object.")

    payload = {
        'discriminator': int(getattr(user, 'discriminator', 0)),
        'id': user.id,
        'in_guild': False,
        'name': getattr(user, 'name', 'Name unknown'),
        'roles': []
    }

    try:
        response = await ctx.bot.api_client.post('bot/users', json=payload)
        log.info(f"User {user.id} added to the DB.")
        return response
    except ResponseCodeError as e:
        log.error(f"Failed to add user {user.id} to the DB. {e}")
        await ctx.send(f":x: The attempt to add the user to the DB failed: status {e.status}")


async def post_infraction(
    ctx: Context,
    user: UserSnowflake,
    infr_type: str,
    reason: str,
    expires_at: datetime = None,
    hidden: bool = False,
    active: bool = True
) -> t.Optional[dict]:
    """Posts an infraction to the API."""
    if isinstance(user, (discord.Member, discord.User)) and user.bot:
        log.trace(f"Posting of {infr_type} infraction for {user} to the API aborted. User is a bot.")
        raise InvalidInfractedUser(user)

    log.trace(f"Posting {infr_type} infraction for {user} to the API.")

    payload = {
        "actor": ctx.author.id,  # Don't use ctx.message.author; antispam only patches ctx.author.
        "hidden": hidden,
        "reason": reason,
        "type": infr_type,
        "user": user.id,
        "active": active
    }
    if expires_at:
        payload['expires_at'] = expires_at.isoformat()

    # Try to apply the infraction. If it fails because the user doesn't exist, try to add it.
    for should_post_user in (True, False):
        try:
            response = await ctx.bot.api_client.post('bot/infractions', json=payload)
            return response
        except ResponseCodeError as e:
            if e.status == 400 and 'user' in e.response_json:
                # Only one attempt to add the user to the database, not two:
                if not should_post_user or await post_user(ctx, user) is None:
                    return
            else:
                log.exception(f"Unexpected error while adding an infraction for {user}:")
                await ctx.send(f":x: There was an error adding the infraction: status {e.status}.")
                return


async def get_active_infraction(
        ctx: Context,
        user: UserSnowflake,
        infr_type: str,
        send_msg: bool = True
) -> t.Optional[dict]:
    """
    Retrieves an active infraction of the given type for the user.

    If `send_msg` is True and the user has an active infraction matching the `infr_type` parameter,
    then a message for the moderator will be sent to the context channel letting them know.
    Otherwise, no message will be sent.
    """
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
        # Checks to see if the moderator should be told there is an active infraction
        if send_msg:
            log.trace(f"{user} has active infractions of type {infr_type}.")
            await ctx.send(
                f":x: According to my records, this user already has a {infr_type} infraction. "
                f"See infraction **#{active_infractions[0]['id']}**."
            )
        return active_infractions[0]
    else:
        log.trace(f"{user} does not have active infractions of type {infr_type}.")


async def notify_infraction(
    user: UserObject,
    infr_type: str,
    expires_at: t.Optional[str] = None,
    reason: t.Optional[str] = None,
    icon_url: str = Icons.token_removed
) -> bool:
    """DM a user about their new infraction and return True if the DM is successful."""
    log.trace(f"Sending {user} a DM about their {infr_type} infraction.")

    text = INFRACTION_DESCRIPTION_TEMPLATE.format(
        type=infr_type.title(),
        expires=expires_at or "N/A",
        reason=reason or "No reason provided."
    )

    # For case when other fields than reason is too long and this reach limit, then force-shorten string
    if len(text) > 2048:
        text = f"{text[:2045]}..."

    embed = discord.Embed(
        description=text,
        colour=Colours.soft_red
    )

    embed.set_author(name=INFRACTION_AUTHOR_NAME, icon_url=icon_url, url=RULES_URL)
    embed.title = INFRACTION_TITLE
    embed.url = RULES_URL

    if infr_type in APPEALABLE_INFRACTIONS:
        embed.set_footer(text=INFRACTION_APPEAL_FOOTER)

    return await send_private_embed(user, embed)


async def notify_pardon(
    user: UserObject,
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


async def send_private_embed(user: UserObject, embed: discord.Embed) -> bool:
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
