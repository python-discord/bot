import re
from datetime import timedelta

import arrow
from disnake import Forbidden, http
from disnake.ext import commands

from bot.log import get_logger

log = get_logger(__name__)
MESSAGE_ID_RE = re.compile(r'(?P<message_id>[0-9]{15,20})$')


class Command(commands.Command):
    """
    A `disnake.ext.commands.Command` subclass which supports root aliases.

    A `root_aliases` keyword argument is added, which is a sequence of alias names that will act as
    top-level commands rather than being aliases of the command's group. It's stored as an attribute
    also named `root_aliases`.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root_aliases = kwargs.get("root_aliases", [])

        if not isinstance(self.root_aliases, (list, tuple)):
            raise TypeError("Root aliases of a command must be a list or a tuple of strings.")


def patch_typing() -> None:
    """
    Sometimes discord turns off typing events by throwing 403's.

    Handle those issues by patching the trigger_typing method so it ignores 403's in general.
    """
    log.debug("Patching send_typing, which should fix things breaking when discord disables typing events. Stay safe!")

    original = http.HTTPClient.send_typing
    last_403 = None

    async def honeybadger_type(self, channel_id: int) -> None:  # noqa: ANN001
        nonlocal last_403
        if last_403 and (arrow.utcnow() - last_403) < timedelta(minutes=5):
            log.warning("Not sending typing event, we got a 403 less than 5 minutes ago.")
            return
        try:
            await original(self, channel_id)
        except Forbidden:
            last_403 = arrow.utcnow()
            log.warning("Got a 403 from typing event!")
            pass

    http.HTTPClient.send_typing = honeybadger_type


class FixedPartialMessageConverter(commands.PartialMessageConverter):
    """
    Make the Message converter infer channelID from the given context if only a messageID is given.

    Discord.py's Message converter is supposed to infer channelID based
    on ctx.channel if only a messageID is given. A refactor commit, linked below,
    a few weeks before d.py's archival broke this defined behaviour of the converter.
    Currently, if only a messageID is given to the converter, it will only find that message
    if it's in the bot's cache.

    https://github.com/Rapptz/discord.py/commit/1a4e73d59932cdbe7bf2c281f25e32529fc7ae1f
    """

    @staticmethod
    def _get_id_matches(ctx: commands.Context, argument: str) -> tuple[int, int, int]:
        """Inserts ctx.channel.id before calling super method if argument is just a messageID."""
        match = MESSAGE_ID_RE.match(argument)
        if match:
            argument = f"{ctx.channel.id}-{match.group('message_id')}"
        return commands.PartialMessageConverter._get_id_matches(ctx, argument)
