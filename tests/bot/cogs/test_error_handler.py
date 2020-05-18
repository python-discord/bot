import unittest

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
