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
        self.cog = ErrorHandler(self.bot)

    async def test_error_handler_already_handled(self):
        """Should not do anything when error is already handled by local error handler."""
        error = errors.CommandError()
        error.handled = "foo"
        await self.cog.on_command_error(self.ctx, error)
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
        self.cog.try_silence = AsyncMock()
        self.cog.try_get_tag = AsyncMock()

        for case in test_cases:
            with self.subTest(try_silence_return=case["try_silence_return"], try_get_tag=case["called_try_get_tag"]):
                self.ctx.reset_mock()
                self.cog.try_silence.reset_mock(return_value=True)
                self.cog.try_get_tag.reset_mock()

                self.cog.try_silence.return_value = case["try_silence_return"]
                self.ctx.channel.id = 1234

                if case["patch_verification_id"]:
                    with patch("bot.cogs.error_handler.Channels.verification", new=1234):
                        self.assertIsNone(await self.cog.on_command_error(self.ctx, error))
                else:
                    self.assertIsNone(await self.cog.on_command_error(self.ctx, error))
                if case["try_silence_return"]:
                    self.cog.try_get_tag.assert_not_awaited()
                    self.cog.try_silence.assert_awaited_once()
                else:
                    self.cog.try_silence.assert_awaited_once()
                    if case["patch_verification_id"]:
                        self.cog.try_get_tag.assert_not_awaited()
                    else:
                        self.cog.try_get_tag.assert_awaited_once()
                self.ctx.send.assert_not_awaited()
