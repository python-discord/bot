from typing import Callable, Iterable

from discord import Guild
from discord.ext.commands import Bot

from . import syncers


class Sync:
    """Captures relevant events and sends them to the site."""

    # The server to synchronize events on.
    # Note that setting this wrongly will result in things getting deleted
    # that possibly shouldn't be.
    SYNC_SERVER_ID = 267624335836053506

    # An iterable of callables that are called when the bot is ready.
    ON_READY_SYNCERS: Iterable[Callable[[Bot, Guild], None]] = (
        syncers.sync_roles,
    )

    def __init__(self, bot):
        self.bot = bot

    async def on_ready(self):
        guild = self.bot.get_guild(self.SYNC_SERVER_ID)
        if guild is not None:
            for syncer in self.ON_READY_SYNCERS:
                await syncer(self.bot, guild)
