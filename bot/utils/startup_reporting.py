from collections.abc import Mapping
from typing import TYPE_CHECKING

import discord

from bot.constants import Channels, Icons
from bot.log import get_logger

log = get_logger(__name__)

if TYPE_CHECKING:
    from bot.bot import Bot

class StartupFailureReporter:
    """Formats and sends one aggregated startup failure alert to moderators."""

    async def notify(self, bot: Bot, failures: Mapping[str, BaseException], channel_id: int = Channels.mod_log) -> None:
        """Notify moderators of startup failures."""
        if not failures:
            return

        if bot.get_channel(channel_id) is None:
            # Can't send a message if the channel doesn't exist, so log instead
            log.warning("Failed to send startup failure report: mod_log channel not found.")
            return

        try:
            # Local import avoids circular dependency
            from bot.utils.modlog import send_log_message

            text = self.render(failures)

            await send_log_message(
                bot,
                icon_url=Icons.token_removed,
                colour=discord.Colour.red(),
                title="Startup: Some extensions failed to load",
                text=text,
                ping_everyone=True,
                channel_id=channel_id
            )
        except Exception as exception:
            log.exception(f"Failed to send startup failure report: {exception}")

    def render(self, failures: Mapping[str, BaseException]) -> str:
        """Render a human-readable message from the given failures."""
        failure_keys = sorted(failures.keys())

        lines = []
        lines.append("The following extension(s) failed to load:")
        for failure_key in failure_keys:
            exception = failures[failure_key]
            lines.append(f"- **{failure_key}** - `{type(exception).__name__}: {exception}`")

        return "\n".join(lines)
