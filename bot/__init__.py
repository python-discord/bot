import asyncio
import os
from functools import partial, partialmethod
from typing import TYPE_CHECKING

from discord.ext import commands

from bot import log, monkey_patches

if TYPE_CHECKING:
    from bot.bot import Bot

log.setup()

# On Windows, the selector event loop is required for aiodns.
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

monkey_patches.patch_typing()

# Monkey-patch discord.py decorators to use the Command subclass which supports root aliases.
# Must be patched before any cogs are added.
commands.command = partial(commands.command, cls=monkey_patches.Command)
commands.GroupMixin.command = partialmethod(
    commands.GroupMixin.command, cls=monkey_patches.Command
)

instance: "Bot" = None  # Global Bot instance.
