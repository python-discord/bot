import unittest
from unittest.mock import AsyncMock, patch

from discord.ext.commands import errors

from bot.cogs.error_handler import ErrorHandler
from tests.helpers import MockBot, MockContext


class ErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Tests for error handler functionality."""

    def setUp(self):
        self.bot = MockBot()
        self.ctx = MockContext(bot=self.bot)

    async def test_error_handler_already_handled(self):
        """Should not do anything when error is already handled by local error handler."""
        cog = ErrorHandler(self.bot)
        error = errors.CommandError()
        error.handled = "foo"
        self.assertIsNone(await cog.on_command_error(self.ctx, error))
        self.ctx.send.assert_not_awaited()

    async def test_error_handler_command_not_found_error_not_invoked_by_handler(self):
        """Should try first (un)silence channel, when fail and channel is not verification channel try to get tag."""
        error = errors.CommandNotFound()
        test_cases = (
            {
                "try_silence_return": True,
                "patch_verification_id": False,
                "called_try_get_tag": False
            },
            {
                "try_silence_return": False,
                "patch_verification_id": True,
                "called_try_get_tag": False
            },
            {
                "try_silence_return": False,
                "patch_verification_id": False,
                "called_try_get_tag": True
            }
        )
        cog = ErrorHandler(self.bot)
        cog.try_silence = AsyncMock()
        cog.try_get_tag = AsyncMock()

        for case in test_cases:
            with self.subTest(try_silence_return=case["try_silence_return"], try_get_tag=case["called_try_get_tag"]):
                self.ctx.reset_mock()
                cog.try_silence.reset_mock(return_value=True)
                cog.try_get_tag.reset_mock()

                cog.try_silence.return_value = case["try_silence_return"]
                self.ctx.channel.id = 1234

                if case["patch_verification_id"]:
                    with patch("bot.cogs.error_handler.Channels.verification", new=1234):
                        self.assertIsNone(await cog.on_command_error(self.ctx, error))
                else:
                    self.assertIsNone(await cog.on_command_error(self.ctx, error))
                if case["try_silence_return"]:
                    cog.try_get_tag.assert_not_awaited()
                    cog.try_silence.assert_awaited_once()
                else:
                    cog.try_silence.assert_awaited_once()
                    if case["patch_verification_id"]:
                        cog.try_get_tag.assert_not_awaited()
                    else:
                        cog.try_get_tag.assert_awaited_once()
                self.ctx.send.assert_not_awaited()
