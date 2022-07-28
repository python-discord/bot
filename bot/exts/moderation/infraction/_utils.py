import typing as t
from datetime import datetime, timezone

import arrow
import discord
from botcore.site_api import ResponseCodeError
from discord.ext.commands import Context

import bot
from bot.constants import Colours, Icons
from bot.converters import DurationOrExpiry, MemberOrUser
from bot.errors import InvalidInfractedUserError
from bot.log import get_logger
from bot.utils import time

log = get_logger(__name__)

# apply icon, pardon icon
INFRACTION_ICONS = {
    "ban": (Icons.user_ban, Icons.user_unban),
    "kick": (Icons.sign_out, None),
    "mute": (Icons.user_mute, Icons.user_unmute),
    "note": (Icons.user_warn, None),
    "superstar": (Icons.superstarify, Icons.unsuperstarify),
    "warning": (Icons.user_warn, None),
    "voice_mute": (Icons.voice_state_red, Icons.voice_state_green),
}
RULES_URL = "https://pythondiscord.com/pages/rules"

# Type aliases
Infraction = t.Dict[str, t.Union[str, int, bool]]

APPEAL_SERVER_INVITE = "https://discord.gg/WXrCJxWBnm"

INFRACTION_TITLE = "Please review our rules"
INFRACTION_APPEAL_SERVER_FOOTER = f"\nTo appeal this infraction, join our [appeals server]({APPEAL_SERVER_INVITE})."
INFRACTION_APPEAL_MODMAIL_FOOTER = (
    '\nIf you would like to discuss or appeal this infraction, '
    'send a message to the ModMail bot.'
)
INFRACTION_AUTHOR_NAME = "Infraction information"

LONGEST_EXTRAS = max(len(INFRACTION_APPEAL_SERVER_FOOTER), len(INFRACTION_APPEAL_MODMAIL_FOOTER))

INFRACTION_DESCRIPTION_TEMPLATE = (
    "**Type:** {type}\n"
    "**Expires:** {expires}\n"
    "**Duration:** {duration}\n"
    "**Reason:** {reason}\n"
)


async def post_user(ctx: Context, user: MemberOrUser) -> t.Optional[dict]:
    """
    Create a new user in the database.

    Used when an infraction needs to be applied on a user absent in the guild.
    """
    log.trace(f"Attempting to add user {user.id} to the database.")

    payload = {
        'discriminator': int(user.discriminator),
        'id': user.id,
        'in_guild': False,
        'name': user.name,
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
        user: MemberOrUser,
        infr_type: str,
        reason: str,
        duration_or_expiry: t.Optional[DurationOrExpiry] = None,
        hidden: bool = False,
        active: bool = True,
        dm_sent: bool = False,
) -> t.Optional[dict]:
    """Posts an infraction to the API."""
    if isinstance(user, (discord.Member, discord.User)) and user.bot:
        log.trace(f"Posting of {infr_type} infraction for {user} to the API aborted. User is a bot.")
        raise InvalidInfractedUserError(user)

    log.trace(f"Posting {infr_type} infraction for {user} to the API.")

    current_time = datetime.now(tz=timezone.utc)

    payload = {
        "actor": ctx.author.id,  # Don't use ctx.message.author; antispam only patches ctx.author.
        "hidden": hidden,
        "reason": reason,
        "type": infr_type,
        "user": user.id,
        "active": active,
        "dm_sent": dm_sent,
        "last_applied": current_time.isoformat(),
    }

    # Parse duration or expiry
    if duration_or_expiry is not None:
        if isinstance(duration_or_expiry, datetime):
            payload['expires_at'] = duration_or_expiry.isoformat()
        else:  # is relativedelta
            payload['expires_at'] = (current_time + duration_or_expiry).isoformat()

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
        user: MemberOrUser,
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
            await send_active_infraction_message(ctx, active_infractions[0])
        return active_infractions[0]
    else:
        log.trace(f"{user} does not have active infractions of type {infr_type}.")


async def send_active_infraction_message(ctx: Context, infraction: Infraction) -> None:
    """Send a message stating that the given infraction is active."""
    await ctx.send(
        f":x: According to my records, this user already has a {infraction['type']} infraction. "
        f"See infraction **#{infraction['id']}**."
    )


async def notify_infraction(
        infraction: Infraction,
        user: MemberOrUser,
        reason: t.Optional[str] = None
) -> bool:
    """
    DM a user about their new infraction and return True if the DM is successful.

    `reason` can be used to override what is in `infraction`. Otherwise, this data will
    be retrieved from `infraction`.
    """
    infr_id = infraction["id"]
    infr_type = infraction["type"].replace("_", " ").title()
    icon_url = INFRACTION_ICONS[infraction["type"]][0]

    if infraction["expires_at"] is None:
        expires_at = "Never"
        duration = "Permanent"
    else:
        expiry = arrow.get(infraction["expires_at"])
        expires_at = time.format_relative(expiry)
        duration = time.humanize_delta(infraction["inserted_at"], expiry, max_units=2)

        if infraction["active"]:
            remaining = time.humanize_delta(expiry, arrow.utcnow(), max_units=2)
            if duration != remaining:
                duration += f" ({remaining} remaining)"
        else:
            expires_at += " (Inactive)"

    log.trace(f"Sending {user} a DM about their {infr_type} infraction.")

    if reason is None:
        reason = infraction["reason"]

    text = INFRACTION_DESCRIPTION_TEMPLATE.format(
        type=infr_type.title(),
        expires=expires_at,
        duration=duration,
        reason=reason or "No reason provided."
    )

    # For case when other fields than reason is too long and this reach limit, then force-shorten string
    if len(text) > 4096 - LONGEST_EXTRAS:
        text = f"{text[:4093-LONGEST_EXTRAS]}..."

    text += INFRACTION_APPEAL_SERVER_FOOTER if infraction["type"] == 'ban' else INFRACTION_APPEAL_MODMAIL_FOOTER

    embed = discord.Embed(
        description=text,
        colour=Colours.soft_red
    )

    embed.set_author(name=INFRACTION_AUTHOR_NAME, icon_url=icon_url, url=RULES_URL)
    embed.title = INFRACTION_TITLE
    embed.url = RULES_URL

    dm_sent = await send_private_embed(user, embed)
    if dm_sent:
        await bot.instance.api_client.patch(
            f"bot/infractions/{infr_id}",
            json={"dm_sent": True}
        )
        log.debug(f"Update infraction #{infr_id} dm_sent field to true.")

    return dm_sent


async def notify_pardon(
        user: MemberOrUser,
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


async def send_private_embed(user: MemberOrUser, embed: discord.Embed) -> bool:
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
