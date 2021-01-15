import json
import logging
import typing as t
from collections import deque
from pathlib import Path

import discord

from bot import constants
from bot.exts.help_channels._channel import MAX_CHANNELS_PER_CATEGORY, get_category_channels

log = logging.getLogger(__name__)


def create_name_queue(*categories: discord.CategoryChannel) -> deque:
    """
    Return a queue of element names to use for creating new channels.

    Skip names that are already in use by channels in `categories`.
    """
    log.trace("Creating the chemical element name queue.")

    used_names = _get_used_names(*categories)

    log.trace("Determining the available names.")
    available_names = (name for name in _get_names() if name not in used_names)

    log.trace("Populating the name queue with names.")
    return deque(available_names)


def _get_names() -> t.List[str]:
    """
    Return a truncated list of prefixed element names.

    The amount of names is configured with `HelpChannels.max_total_channels`.
    The prefix is configured with `HelpChannels.name_prefix`.
    """
    count = constants.HelpChannels.max_total_channels
    prefix = constants.HelpChannels.name_prefix

    log.trace(f"Getting the first {count} element names from JSON.")

    with Path("bot/resources/elements.json").open(encoding="utf-8") as elements_file:
        all_names = json.load(elements_file)

    if prefix:
        return [prefix + name for name in all_names[:count]]
    else:
        return all_names[:count]


def _get_used_names(*categories: discord.CategoryChannel) -> t.Set[str]:
    """Return names which are already being used by channels in `categories`."""
    log.trace("Getting channel names which are already being used.")

    names = set()
    for cat in categories:
        for channel in get_category_channels(cat):
            names.add(channel.name)

    if len(names) > MAX_CHANNELS_PER_CATEGORY:
        log.warning(
            f"Too many help channels ({len(names)}) already exist! "
            f"Discord only supports {MAX_CHANNELS_PER_CATEGORY} in a category."
        )

    log.trace(f"Got {len(names)} used names: {names}")
    return names
