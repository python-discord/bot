import asyncio
import os
from typing import TYPE_CHECKING

from pydis_core.utils import apply_monkey_patches

from bot import log

if TYPE_CHECKING:
    from bot.bot import Bot

log.setup()

# On Windows, the selector event loop is required for aiodns.
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

apply_monkey_patches()

instance: "Bot" = None  # Global Bot instance.
