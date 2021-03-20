import logging

from more_itertools import ilen

import bot
from bot import constants
from bot.exts.help_channels import _caches, _channel

log = logging.getLogger(__name__)


def report_counts() -> None:
    """Report channel count stats of each help category."""
    for name in ("in_use", "available", "dormant"):
        id_ = getattr(constants.Categories, f"help_{name}")
        category = bot.instance.get_channel(id_)

        if category:
            total = ilen(_channel.get_category_channels(category))
            bot.instance.stats.gauge(f"help.total.{name}", total)
        else:
            log.warning(f"Couldn't find category {name!r} to track channel count stats.")


async def report_complete_session(channel_id: int, closed_on: str) -> None:
    """
    Report stats for a completed help session channel `channel_id`.

    Set `is_auto` to True if the channel was automatically closed or False if manually closed.
    """
    caller = f"auto.{closed_on}" if closed_on else "command"
    bot.instance.stats.incr(f"help.dormant_calls.{caller}")

    in_use_time = await _channel.get_in_use_time(channel_id)
    if in_use_time:
        bot.instance.stats.timing("help.in_use_time", in_use_time)

    non_claimant_last_message_time = await _caches.non_claimant_last_message_times.get(channel_id)
    if non_claimant_last_message_time is None:
        bot.instance.stats.incr("help.sessions.unanswered")
    else:
        bot.instance.stats.incr("help.sessions.answered")
