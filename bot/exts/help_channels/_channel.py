"""Contains all logic to handle changes to posts in the help forum."""
import asyncio
import textwrap

import discord
from botcore.utils import members

import bot
from bot import constants
from bot.exts.help_channels import _stats
from bot.log import get_logger

log = get_logger(__name__)

ASKING_GUIDE_URL = "https://pythondiscord.com/pages/asking-good-questions/"

POST_TITLE = "Python help channel"
NEW_POST_MSG = f"""
**Remember to:**
• **Ask** your Python question, not if you can ask or if there's an expert who can help.
• **Show** a code sample as text (rather than a screenshot) and the error message, if you got one.
• **Explain** what you expect to happen and what actually happens.

For more tips, check out our guide on [asking good questions]({ASKING_GUIDE_URL}).
"""
POST_FOOTER = f"Closes after a period of inactivity, or when you send {constants.Bot.prefix}close."

DORMANT_MSG = f"""
This help channel has been marked as **dormant** and locked. \
It is no longer possible to send messages in this channel.

If your question wasn't answered yet, you can create a new post in <#{constants.Channels.help_system_forum}>. \
Consider rephrasing the question to maximize your chance of getting a good answer. \
If you're not sure how, have a look through our guide for **[asking a good question]({ASKING_GUIDE_URL})**.
"""


def is_help_forum_post(channel: discord.abc.GuildChannel) -> bool:
    """Return True if `channel` is a post in the help forum."""
    log.trace(f"Checking if #{channel} is a help channel.")
    return getattr(channel, "parent_id", None) == constants.Channels.help_system_forum


async def _close_help_thread(closed_thread: discord.Thread, closed_on: _stats.ClosingReason) -> None:
    """Close the help thread and record stats."""
    embed = discord.Embed(description=DORMANT_MSG)
    await closed_thread.send(embed=embed)
    await closed_thread.edit(archived=True, locked=True, reason="Locked a dormant help channel")

    _stats.report_post_count()
    await _stats.report_complete_session(closed_thread, closed_on)

    poster = closed_thread.owner
    cooldown_role = closed_thread.guild.get_role(constants.Roles.help_cooldown)

    if poster is None:
        # We can't include the owner ID/name here since the thread only contains None
        log.info(
            f"Failed to remove cooldown role for owner of thread ({closed_thread.id}). "
            f"The user is likely no longer on the server."
        )
        return

    await members.handle_role_change(poster, poster.remove_roles, cooldown_role)


async def send_opened_post_message(thread: discord.Thread) -> None:
    """Send the opener message in the new help post."""
    embed = discord.Embed(
        color=constants.Colours.bright_green,
        description=NEW_POST_MSG,
    )
    embed.set_author(name=POST_TITLE)
    embed.set_footer(text=POST_FOOTER)
    await thread.send(embed=embed)


async def send_opened_post_dm(thread: discord.Thread) -> None:
    """Send the opener a DM message with a jump link to their new post."""
    embed = discord.Embed(
        title="Help channel opened",
        description=f"You opened {thread.mention}.",
        colour=constants.Colours.bright_green,
        timestamp=thread.created_at,
    )
    embed.set_thumbnail(url=constants.Icons.green_questionmark)
    message = thread.starter_message
    if not message:
        try:
            message = await thread.fetch_message(thread.id)
        except discord.HTTPException:
            log.warning(f"Could not fetch message for thread {thread.id}")
            return

    formatted_message = textwrap.shorten(message.content, width=100, placeholder="...").strip()
    if formatted_message is None:
        # This most likely means the initial message is only an image or similar
        formatted_message = "No text content."

    embed.add_field(name="Your message", value=formatted_message, inline=False)
    embed.add_field(
        name="Conversation",
        value=f"[Jump to message!]({message.jump_url})",
        inline=False,
    )

    try:
        await thread.owner.send(embed=embed)
        log.trace(f"Sent DM to {thread.owner} ({thread.owner_id}) after posting in help forum.")
    except discord.errors.Forbidden:
        log.trace(
            f"Ignoring to send DM to {thread.owner} ({thread.owner_id}) after posting in help forum: DMs disabled.",
        )


async def help_thread_opened(opened_thread: discord.Thread, *, reopen: bool = False) -> None:
    """Apply new post logic to a new help forum post."""
    _stats.report_post_count()

    if not isinstance(opened_thread.owner, discord.Member):
        log.debug(f"{opened_thread.owner_id} isn't a member. Closing post.")
        await _close_help_thread(opened_thread, _stats.ClosingReason.CLEANUP)
        return

    # Discord sends the open event long before the thread is ready for actions in the API.
    # This causes actions such as fetching the message, pinning message, etc to fail.
    # We sleep here to try and delay our code enough so the thread is ready in the API.
    await asyncio.sleep(2)

    await send_opened_post_dm(opened_thread)

    try:
        await opened_thread.starter_message.pin()
    except discord.HTTPException as e:
        if e.code == 10008:
            # The message was not found, most likely deleted
            pass
        else:
            raise e

    await send_opened_post_message(opened_thread)

    cooldown_role = opened_thread.guild.get_role(constants.Roles.help_cooldown)
    await members.handle_role_change(opened_thread.owner, opened_thread.owner.add_roles, cooldown_role)


async def help_thread_closed(closed_thread: discord.Thread) -> None:
    """Apply archive logic to a manually closed help forum post."""
    await _close_help_thread(closed_thread, _stats.ClosingReason.COMMAND)


async def help_thread_archived(archived_thread: discord.Thread) -> None:
    """Apply archive logic to an archived help forum post."""
    async for thread_update in archived_thread.guild.audit_logs(limit=50, action=discord.AuditLogAction.thread_update):
        if thread_update.target.id != archived_thread.id:
            continue

        # Don't apply close logic if the post was archived by the bot, as it
        # would have been done so via _close_help_thread.
        if thread_update.user.id == bot.instance.user.id:
            return

    await _close_help_thread(archived_thread, _stats.ClosingReason.INACTIVE)


async def help_thread_deleted(deleted_thread_event: discord.RawThreadDeleteEvent) -> None:
    """Record appropriate stats when a help thread is deleted."""
    _stats.report_post_count()
    cached_thread = deleted_thread_event.thread
    if cached_thread and not cached_thread.archived:
        # If the thread is in the bot's cache, and it was not archived before deleting, report a complete session.
        await _stats.report_complete_session(cached_thread, _stats.ClosingReason.DELETED)
