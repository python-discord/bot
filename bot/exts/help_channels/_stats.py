from enum import Enum

import arrow
import discord

import bot
from bot import constants
from bot.log import get_logger

log = get_logger(__name__)


class ClosingReason(Enum):
    """All possible closing reasons for help channels."""

    COMMAND = "command"
    INACTIVE = "auto.inactive"
    DELETED = "auto.deleted"
    CLEANUP = "auto.cleanup"


def report_post_count() -> None:
    """Report post count stats of the help forum."""
    help_forum = bot.instance.get_channel(constants.Channels.help_system_forum)
    bot.instance.stats.gauge("help_forum.total.in_use", len(help_forum.threads))


async def report_complete_session(help_session_post: discord.Thread, closed_on: ClosingReason) -> None:
    """
    Report stats for a completed help session post `help_session_post`.

    `closed_on` is the reason why the post was closed. See `ClosingReason` for possible reasons.
    """
    bot.instance.stats.incr(f"help_forum.dormant_calls.{closed_on.value}")

    open_time = discord.utils.snowflake_time(help_session_post.id)
    in_use_time = arrow.utcnow() - open_time
    bot.instance.stats.timing("help_forum.in_use_time", in_use_time)

    if set(help_session_post.members)-{help_session_post.owner_id} == set():
        # Can't use len(help_session_post.members) as the claimant (owner) may have left the thread.
        bot.instance.stats.incr("help_forum.sessions.unanswered")
    else:
        bot.instance.stats.incr("help_forum.sessions.answered")
