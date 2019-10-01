"""
# message_edited_at patch.

Date: 2019-09-16
Author: Scragly
Added by: Ves Zappa

Due to a bug in our current version of discord.py (1.2.3), the edited_at timestamp of
`discord.Messages` are not being handled correctly. This patch fixes that until a new
release of discord.py is released (and we've updated to it).
"""
import logging

from discord import message, utils

log = logging.getLogger(__name__)


def _handle_edited_timestamp(self: message.Message, value: str) -> None:
    """Helper function that takes care of parsing the edited timestamp."""
    self._edited_timestamp = utils.parse_time(value)


def apply_patch() -> None:
    """Applies the `edited_at` patch to the `discord.message.Message` class."""
    message.Message._handle_edited_timestamp = _handle_edited_timestamp
    message.Message._HANDLERS['edited_timestamp'] = message.Message._handle_edited_timestamp
    log.info("Patch applied: message_edited_at")


if __name__ == "__main__":
    apply_patch()
