"""Contains all logic to handle changes to posts in the help forum."""
from datetime import timedelta

import arrow
import discord
from pydis_core.utils import scheduling
from pydis_core.utils.channel import get_or_fetch_channel

import bot
from bot import constants
from bot.exts.help_channels import _stats
from bot.log import get_logger

log = get_logger(__name__)

ASKING_GUIDE_URL = "https://pythondiscord.com/pages/asking-good-questions/"
BRANDING_REPO_RAW_URL = "https://raw.githubusercontent.com/python-discord/branding"
POST_TITLE = "Python help channel"

NEW_POST_MSG = """
**Remember to:**
- **Ask** your Python question, not if you can ask or if there's an expert who can help.
- **Show** a code sample as text (rather than a screenshot) and the error message, if you've got one.
- **Explain** what you expect to happen and what actually happens.

:warning: Do not pip install anything that isn't related to your question, especially if asked to over DMs.
"""
NEW_POST_FOOTER = f"Closes after a period of inactivity, or when you send {constants.Bot.prefix}close."
NEW_POST_ICON_URL = f"{BRANDING_REPO_RAW_URL}/main/icons/checkmark/green-checkmark-dist.png"

CLOSED_POST_MSG = f"""
This help channel has been closed and it's no longer possible to send messages here. \
If your question wasn't answered, feel free to create a new post in <#{constants.Channels.python_help}>. \
To maximize your chances of getting a response, check out this guide on [asking good questions]({ASKING_GUIDE_URL}).
"""
CLOSED_POST_ICON_URL = f"{BRANDING_REPO_RAW_URL}/main/icons/zzz/zzz-dist.png"


def is_help_forum_post(channel: discord.abc.GuildChannel) -> bool:
    """Return True if `channel` is a post in the help forum."""
    log.trace(f"Checking if #{channel} is a help channel.")
    return getattr(channel, "parent_id", None) == constants.Channels.python_help


async def _close_help_post(closed_post: discord.Thread, closing_reason: _stats.ClosingReason) -> None:
    """Close the help post and record stats."""
    embed = discord.Embed(description=CLOSED_POST_MSG)
    embed.set_author(name=f"{POST_TITLE} closed", icon_url=CLOSED_POST_ICON_URL)
    message = ""

    # Include a ping in the close message if no one else engages, to encourage them
    # to read the guide for asking better questions
    if closing_reason == _stats.ClosingReason.INACTIVE and closed_post.owner is not None:
        participant_ids = {
            message.author.id async for message in closed_post.history(limit=100, oldest_first=False)
            if not message.author.bot
        }
        if participant_ids == {closed_post.owner_id}:
            message = closed_post.owner.mention

    try:
        await closed_post.send(message, embed=embed)
    except discord.errors.HTTPException:
        log.info("Could not send closing message in %s (%d), closing anyway", closed_post, closed_post.id)

    await closed_post.edit(
        name=f"🔒 {closed_post.name}"[:100],
        archived=True,
        locked=True,
        reason="Locked a closed help post",
    )

    _stats.report_post_count()
    await _stats.report_complete_session(closed_post, closing_reason)


async def send_opened_post_message(post: discord.Thread) -> None:
    """Send the opener message in the new help post."""
    embed = discord.Embed(
        color=constants.Colours.bright_green,
        description=NEW_POST_MSG,
    )
    embed.set_author(name=f"{POST_TITLE} opened", icon_url=NEW_POST_ICON_URL)
    embed.set_footer(text=NEW_POST_FOOTER)
    await post.send(embed=embed, content=post.owner.mention)


async def help_post_opened(opened_post: discord.Thread, *, reopen: bool = False) -> None:
    """Apply new post logic to a new help forum post."""
    _stats.report_post_count()
    bot.instance.stats.incr("help.claimed")

    if not isinstance(opened_post.owner, discord.Member):
        log.debug(f"{opened_post.owner_id} isn't a member. Closing post.")
        await _close_help_post(opened_post, _stats.ClosingReason.CLEANUP)
        return

    try:
        await opened_post.starter_message.pin()
    except (discord.HTTPException, AttributeError) as e:
        # Suppress if the message or post were not found, most likely deleted
        # The message being deleted could be surfaced as an AttributeError on .starter_message,
        # or as an exception from the Discord API, depending on timing and cache status.
        # The post being deleting would happen if it had a bad name that would cause the filtering system to delete it.
        if isinstance(e, discord.HTTPException):
            if e.code == 10003:  # Post not found.
                return
            if e.code != 10008:  # 10008 - Starter message not found.
                raise e

    await send_opened_post_message(opened_post)


async def help_post_closed(closed_post: discord.Thread) -> None:
    """Apply archive logic to a manually closed help forum post."""
    await _close_help_post(closed_post, _stats.ClosingReason.COMMAND)


async def help_post_archived(archived_post: discord.Thread) -> None:
    """Apply archive logic to an archived help forum post."""
    async for thread_update in archived_post.guild.audit_logs(limit=50, action=discord.AuditLogAction.thread_update):
        if thread_update.target.id != archived_post.id:
            continue

        # Don't apply close logic if the post was archived by the bot, as it
        # would have been done so via _close_help_thread.
        if thread_update.user.id == bot.instance.user.id:
            return

    await _close_help_post(archived_post, _stats.ClosingReason.INACTIVE)


async def help_post_deleted(deleted_post_event: discord.RawThreadDeleteEvent) -> None:
    """Record appropriate stats when a help post is deleted."""
    _stats.report_post_count()
    cached_post = deleted_post_event.thread
    if cached_post and not cached_post.archived:
        # If the post is in the bot's cache, and it was not archived before deleting,
        # report a complete session.
        await _stats.report_complete_session(cached_post, _stats.ClosingReason.DELETED)


async def get_closing_time(post: discord.Thread) -> tuple[arrow.Arrow, _stats.ClosingReason]:
    """
    Return the time at which the given help `post` should be closed along with the reason.

    The time is calculated by first checking if the opening message is deleted.
    If it is, then get the last 100 messages (the most that can be fetched in one API call).
    If less than 100 message are returned, and none are from the post owner, then assume the poster
        has sent no further messages and close deleted_idle_minutes after the post creation time.

    Otherwise, use the most recent message's create_at date and add `idle_minutes_claimant`.
    """
    try:
        starter_message = post.starter_message or await post.fetch_message(post.id)
    except discord.NotFound:
        starter_message = None

    last_100_messages = [message async for message in post.history(limit=100, oldest_first=False)]

    if starter_message is None and len(last_100_messages) < 100:
        if not discord.utils.get(last_100_messages, author__id=post.owner_id):
            time = arrow.Arrow.fromdatetime(post.created_at)
            time += timedelta(minutes=constants.HelpChannels.deleted_idle_minutes)
            return time, _stats.ClosingReason.DELETED

    time = arrow.Arrow.fromdatetime(last_100_messages[0].created_at)
    time += timedelta(minutes=constants.HelpChannels.idle_minutes)
    return time, _stats.ClosingReason.INACTIVE


async def maybe_archive_idle_post(post: discord.Thread, scheduler: scheduling.Scheduler) -> None:
    """Archive the `post` if idle, or schedule the archive for later if still active."""
    try:
        await get_or_fetch_channel(bot.instance, post.id)
    except discord.HTTPException:
        log.trace(f"Not closing missing post #{post} ({post.id}).")
        return

    if post.locked:
        log.trace(f"Not closing already closed post #{post} ({post.id}).")
        return

    log.trace(f"Handling open post #{post} ({post.id}).")

    closing_time, closing_reason = await get_closing_time(post)

    if closing_time < (arrow.utcnow() + timedelta(seconds=1)):
        # Closing time is in the past.
        # Add 1 second due to POSIX timestamps being lower resolution than datetime objects.
        log.info(
            f"#{post} ({post.id}) is idle past {closing_time} and will be archived. Reason: {closing_reason.value}"
        )
        await _close_help_post(post, closing_reason)
        return

    if post.id in scheduler:
        # Cancel any existing close task
        scheduler.cancel(post.id)
    delay = (closing_time - arrow.utcnow()).seconds
    log.info(f"#{post} ({post.id}) is still active; scheduling it to be archived after {delay} seconds.")

    scheduler.schedule_later(delay, post.id, maybe_archive_idle_post(post, scheduler))
