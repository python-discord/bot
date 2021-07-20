import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

from discord.ext.commands import errors

from bot.api import ResponseCodeError
from bot.errors import InvalidInfractedUserError, LockedResourceError
from bot.exts.backend.error_handler import ErrorHandler, setup
from bot.exts.info.tags import Tags
from bot.exts.moderation.silence import Silence
from bot.utils.checks import InWhitelistCheckFailure
from tests.helpers import MockBot, MockContext, MockGuild, MockRole, MockTextChannel


class ErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Tests for error handler functionality."""

    def setUp(self):
        self.bot = MockBot()
        self.ctx = MockContext(bot=self.bot)

    async def test_error_handler_already_handled(self):
        """Should not do anything when error is already handled by local error handler."""
        self.ctx.reset_mock()
        cog = ErrorHandler(self.bot)
        error = errors.CommandError()
        error.handled = "foo"
        self.assertIsNone(await cog.on_command_error(self.ctx, error))
        self.ctx.send.assert_not_awaited()

    async def test_error_handler_command_not_found_error_not_invoked_by_handler(self):
        """Should try first (un)silence channel, when fail, try to get tag."""
        error = errors.CommandNotFound()
        test_cases = (
            {
                "try_silence_return": True,
                "called_try_get_tag": False
            },
            {
                "try_silence_return": False,
                "called_try_get_tag": False
            },
            {
                "try_silence_return": False,
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

                self.assertIsNone(await cog.on_command_error(self.ctx, error))

                if case["try_silence_return"]:
                    cog.try_get_tag.assert_not_awaited()
                    cog.try_silence.assert_awaited_once()
                else:
                    cog.try_silence.assert_awaited_once()
                    cog.try_get_tag.assert_awaited_once()

                self.ctx.send.assert_not_awaited()

    async def test_error_handler_command_not_found_error_invoked_by_handler(self):
        """Should do nothing when error is `CommandNotFound` and have attribute `invoked_from_error_handler`."""
        ctx = MockContext(bot=self.bot, invoked_from_error_handler=True)

        cog = ErrorHandler(self.bot)
        cog.try_silence = AsyncMock()
        cog.try_get_tag = AsyncMock()

        error = errors.CommandNotFound()

        self.assertIsNone(await cog.on_command_error(ctx, error))

        cog.try_silence.assert_not_awaited()
        cog.try_get_tag.assert_not_awaited()
        self.ctx.send.assert_not_awaited()

    async def test_error_handler_user_input_error(self):
        """Should await `ErrorHandler.handle_user_input_error` when error is `UserInputError`."""
        self.ctx.reset_mock()
        cog = ErrorHandler(self.bot)
        cog.handle_user_input_error = AsyncMock()
        error = errors.UserInputError()
        self.assertIsNone(await cog.on_command_error(self.ctx, error))
        cog.handle_user_input_error.assert_awaited_once_with(self.ctx, error)

    async def test_error_handler_check_failure(self):
        """Should await `ErrorHandler.handle_check_failure` when error is `CheckFailure`."""
        self.ctx.reset_mock()
        cog = ErrorHandler(self.bot)
        cog.handle_check_failure = AsyncMock()
        error = errors.CheckFailure()
        self.assertIsNone(await cog.on_command_error(self.ctx, error))
        cog.handle_check_failure.assert_awaited_once_with(self.ctx, error)

    async def test_error_handler_command_on_cooldown(self):
        """Should send error with `ctx.send` when error is `CommandOnCooldown`."""
        self.ctx.reset_mock()
        cog = ErrorHandler(self.bot)
        error = errors.CommandOnCooldown(10, 9)
        self.assertIsNone(await cog.on_command_error(self.ctx, error))
        self.ctx.send.assert_awaited_once_with(error)

    async def test_error_handler_command_invoke_error(self):
        """Should call `handle_api_error` or `handle_unexpected_error` depending on original error."""
        cog = ErrorHandler(self.bot)
        cog.handle_api_error = AsyncMock()
        cog.handle_unexpected_error = AsyncMock()
        test_cases = (
            {
                "args": (self.ctx, errors.CommandInvokeError(ResponseCodeError(AsyncMock()))),
                "expect_mock_call": cog.handle_api_error
            },
            {
                "args": (self.ctx, errors.CommandInvokeError(TypeError)),
                "expect_mock_call": cog.handle_unexpected_error
            },
            {
                "args": (self.ctx, errors.CommandInvokeError(LockedResourceError("abc", "test"))),
                "expect_mock_call": "send"
            },
            {
                "args": (self.ctx, errors.CommandInvokeError(InvalidInfractedUserError(self.ctx.author))),
                "expect_mock_call": "send"
            }
        )

        for case in test_cases:
            with self.subTest(args=case["args"], expect_mock_call=case["expect_mock_call"]):
                self.ctx.send.reset_mock()
                self.assertIsNone(await cog.on_command_error(*case["args"]))
                if case["expect_mock_call"] == "send":
                    self.ctx.send.assert_awaited_once()
                else:
                    case["expect_mock_call"].assert_awaited_once_with(
                        self.ctx, case["args"][1].original
                    )

    async def test_error_handler_conversion_error(self):
        """Should call `handle_api_error` or `handle_unexpected_error` depending on original error."""
        cog = ErrorHandler(self.bot)
        cog.handle_api_error = AsyncMock()
        cog.handle_unexpected_error = AsyncMock()
        cases = (
            {
                "error": errors.ConversionError(AsyncMock(), ResponseCodeError(AsyncMock())),
                "mock_function_to_call": cog.handle_api_error
            },
            {
                "error": errors.ConversionError(AsyncMock(), TypeError),
                "mock_function_to_call": cog.handle_unexpected_error
            }
        )

        for case in cases:
            with self.subTest(**case):
                self.assertIsNone(await cog.on_command_error(self.ctx, case["error"]))
                case["mock_function_to_call"].assert_awaited_once_with(self.ctx, case["error"].original)

    async def test_error_handler_two_other_errors(self):
        """Should call `handle_unexpected_error` if error is `MaxConcurrencyReached` or `ExtensionError`."""
        cog = ErrorHandler(self.bot)
        cog.handle_unexpected_error = AsyncMock()
        errs = (
            errors.MaxConcurrencyReached(1, MagicMock()),
            errors.ExtensionError(name="foo")
        )

        for err in errs:
            with self.subTest(error=err):
                cog.handle_unexpected_error.reset_mock()
                self.assertIsNone(await cog.on_command_error(self.ctx, err))
                cog.handle_unexpected_error.assert_awaited_once_with(self.ctx, err)

    @patch("bot.exts.backend.error_handler.log")
    async def test_error_handler_other_errors(self, log_mock):
        """Should `log.debug` other errors."""
        cog = ErrorHandler(self.bot)
        error = errors.DisabledCommand()  # Use this just as a other error
        self.assertIsNone(await cog.on_command_error(self.ctx, error))
        log_mock.debug.assert_called_once()


class TrySilenceTests(unittest.IsolatedAsyncioTestCase):
    """Test for helper functions that handle `CommandNotFound` error."""

    def setUp(self):
        self.bot = MockBot()
        self.silence = Silence(self.bot)
        self.bot.get_command.return_value = self.silence.silence
        self.ctx = MockContext(bot=self.bot)
        self.cog = ErrorHandler(self.bot)

    async def test_try_silence_context_invoked_from_error_handler(self):
        """Should set `Context.invoked_from_error_handler` to `True`."""
        self.ctx.invoked_with = "foo"
        await self.cog.try_silence(self.ctx)
        self.assertTrue(hasattr(self.ctx, "invoked_from_error_handler"))
        self.assertTrue(self.ctx.invoked_from_error_handler)

    async def test_try_silence_get_command(self):
        """Should call `get_command` with `silence`."""
        self.ctx.invoked_with = "foo"
        await self.cog.try_silence(self.ctx)
        self.bot.get_command.assert_called_once_with("silence")

    async def test_try_silence_no_permissions_to_run(self):
        """Should return `False` because missing permissions."""
        self.ctx.invoked_with = "foo"
        self.bot.get_command.return_value.can_run = AsyncMock(return_value=False)
        self.assertFalse(await self.cog.try_silence(self.ctx))

    async def test_try_silence_no_permissions_to_run_command_error(self):
        """Should return `False` because `CommandError` raised (no permissions)."""
        self.ctx.invoked_with = "foo"
        self.bot.get_command.return_value.can_run = AsyncMock(side_effect=errors.CommandError())
        self.assertFalse(await self.cog.try_silence(self.ctx))

    async def test_try_silence_silence_duration(self):
        """Should run silence command with correct duration argument."""
        self.bot.get_command.return_value.can_run = AsyncMock(return_value=True)
        test_cases = ("shh", "shhh", "shhhhhh", "shhhhhhhhhhhhhhhhhhh")

        for case in test_cases:
            with self.subTest(message=case):
                self.ctx.reset_mock()
                self.ctx.invoked_with = case
                self.assertTrue(await self.cog.try_silence(self.ctx))
                self.ctx.invoke.assert_awaited_once_with(
                    self.bot.get_command.return_value,
                    duration_or_channel=None,
                    duration=min(case.count("h")*2, 15),
                    kick=False
                )

    async def test_try_silence_silence_arguments(self):
        """Should run silence with the correct channel, duration, and kick arguments."""
        self.bot.get_command.return_value.can_run = AsyncMock(return_value=True)

        test_cases = (
            (MockTextChannel(), None),  # None represents the case when no argument is passed
            (MockTextChannel(), False),
            (MockTextChannel(), True)
        )

        for channel, kick in test_cases:
            with self.subTest(kick=kick, channel=channel):
                self.ctx.reset_mock()
                self.ctx.invoked_with = "shh"

                self.ctx.message.content = f"!shh {channel.name} {kick if kick is not None else ''}"
                self.ctx.guild.text_channels = [channel]

                self.assertTrue(await self.cog.try_silence(self.ctx))
                self.ctx.invoke.assert_awaited_once_with(
                    self.bot.get_command.return_value,
                    duration_or_channel=channel,
                    duration=4,
                    kick=(kick if kick is not None else False)
                )

    async def test_try_silence_silence_message(self):
        """If the words after the command could not be converted to a channel, None should be passed as channel."""
        self.bot.get_command.return_value.can_run = AsyncMock(return_value=True)
        self.ctx.invoked_with = "shh"
        self.ctx.message.content = "!shh not_a_channel true"

        self.assertTrue(await self.cog.try_silence(self.ctx))
        self.ctx.invoke.assert_awaited_once_with(
            self.bot.get_command.return_value,
            duration_or_channel=None,
            duration=4,
            kick=False
        )

    async def test_try_silence_unsilence(self):
        """Should call unsilence command with correct duration and channel arguments."""
        self.silence.silence.can_run = AsyncMock(return_value=True)
        test_cases = (
            ("unshh", None),
            ("unshhhhh", None),
            ("unshhhhhhhhh", None),
            ("unshh", MockTextChannel())
        )

        for invoke, channel in test_cases:
            with self.subTest(message=invoke, channel=channel):
                self.bot.get_command.side_effect = (self.silence.silence, self.silence.unsilence)
                self.ctx.reset_mock()

                self.ctx.invoked_with = invoke
                self.ctx.message.content = f"!{invoke}"
                if channel is not None:
                    self.ctx.message.content += f" {channel.name}"
                    self.ctx.guild.text_channels = [channel]

                self.assertTrue(await self.cog.try_silence(self.ctx))
                self.ctx.invoke.assert_awaited_once_with(self.silence.unsilence, channel=channel)

    async def test_try_silence_unsilence_message(self):
        """If the words after the command could not be converted to a channel, None should be passed as channel."""
        self.silence.silence.can_run = AsyncMock(return_value=True)
        self.bot.get_command.side_effect = (self.silence.silence, self.silence.unsilence)

        self.ctx.invoked_with = "unshh"
        self.ctx.message.content = "!unshh not_a_channel"

        self.assertTrue(await self.cog.try_silence(self.ctx))
        self.ctx.invoke.assert_awaited_once_with(self.silence.unsilence, channel=None)

    async def test_try_silence_no_match(self):
        """Should return `False` when message don't match."""
        self.ctx.invoked_with = "foo"
        self.assertFalse(await self.cog.try_silence(self.ctx))


class TryGetTagTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `try_get_tag` function."""

    def setUp(self):
        self.bot = MockBot()
        self.ctx = MockContext()
        self.tag = Tags(self.bot)
        self.cog = ErrorHandler(self.bot)
        self.bot.get_command.return_value = self.tag.get_command

    async def test_try_get_tag_get_command(self):
        """Should call `Bot.get_command` with `tags get` argument."""
        self.bot.get_command.reset_mock()
        self.ctx.invoked_with = "foo"
        await self.cog.try_get_tag(self.ctx)
        self.bot.get_command.assert_called_once_with("tags get")

    async def test_try_get_tag_invoked_from_error_handler(self):
        """`self.ctx` should have `invoked_from_error_handler` `True`."""
        self.ctx.invoked_from_error_handler = False
        self.ctx.invoked_with = "foo"
        await self.cog.try_get_tag(self.ctx)
        self.assertTrue(self.ctx.invoked_from_error_handler)

    async def test_try_get_tag_no_permissions(self):
        """Test how to handle checks failing."""
        self.tag.get_command.can_run = AsyncMock(return_value=False)
        self.ctx.invoked_with = "foo"
        self.assertIsNone(await self.cog.try_get_tag(self.ctx))

    async def test_try_get_tag_command_error(self):
        """Should call `on_command_error` when `CommandError` raised."""
        err = errors.CommandError()
        self.tag.get_command.can_run = AsyncMock(side_effect=err)
        self.cog.on_command_error = AsyncMock()
        self.ctx.invoked_with = "foo"
        self.assertIsNone(await self.cog.try_get_tag(self.ctx))
        self.cog.on_command_error.assert_awaited_once_with(self.ctx, err)

    @patch("bot.exts.backend.error_handler.TagNameConverter")
    async def test_try_get_tag_convert_success(self, tag_converter):
        """Converting tag should successful."""
        self.ctx.invoked_with = "foo"
        tag_converter.convert = AsyncMock(return_value="foo")
        self.assertIsNone(await self.cog.try_get_tag(self.ctx))
        tag_converter.convert.assert_awaited_once_with(self.ctx, "foo")
        self.ctx.invoke.assert_awaited_once()

    @patch("bot.exts.backend.error_handler.TagNameConverter")
    async def test_try_get_tag_convert_fail(self, tag_converter):
        """Converting tag should raise `BadArgument`."""
        self.ctx.reset_mock()
        self.ctx.invoked_with = "bar"
        tag_converter.convert = AsyncMock(side_effect=errors.BadArgument())
        self.assertIsNone(await self.cog.try_get_tag(self.ctx))
        self.ctx.invoke.assert_not_awaited()

    async def test_try_get_tag_ctx_invoke(self):
        """Should call `ctx.invoke` with proper args/kwargs."""
        self.ctx.reset_mock()
        self.ctx.invoked_with = "foo"
        self.assertIsNone(await self.cog.try_get_tag(self.ctx))
        self.ctx.invoke.assert_awaited_once_with(self.tag.get_command, tag_name="foo")

    async def test_dont_call_suggestion_tag_sent(self):
        """Should never call command suggestion if tag is already sent."""
        self.ctx.invoked_with = "foo"
        self.ctx.invoke = AsyncMock(return_value=True)
        self.cog.send_command_suggestion = AsyncMock()

        await self.cog.try_get_tag(self.ctx)
        self.cog.send_command_suggestion.assert_not_awaited()

    @patch("bot.exts.backend.error_handler.MODERATION_ROLES", new=[1234])
    async def test_dont_call_suggestion_if_user_mod(self):
        """Should not call command suggestion if user is a mod."""
        self.ctx.invoked_with = "foo"
        self.ctx.invoke = AsyncMock(return_value=False)
        self.ctx.author.roles = [MockRole(id=1234)]
        self.cog.send_command_suggestion = AsyncMock()

        await self.cog.try_get_tag(self.ctx)
        self.cog.send_command_suggestion.assert_not_awaited()

    async def test_call_suggestion(self):
        """Should call command suggestion if user is not a mod."""
        self.ctx.invoked_with = "foo"
        self.ctx.invoke = AsyncMock(return_value=False)
        self.cog.send_command_suggestion = AsyncMock()

        await self.cog.try_get_tag(self.ctx)
        self.cog.send_command_suggestion.assert_awaited_once_with(self.ctx, "foo")


class IndividualErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Individual error categories handler tests."""

    def setUp(self):
        self.bot = MockBot()
        self.ctx = MockContext(bot=self.bot)
        self.cog = ErrorHandler(self.bot)

    async def test_handle_input_error_handler_errors(self):
        """Should handle each error probably."""
        test_cases = (
            {
                "error": errors.MissingRequiredArgument(MagicMock()),
                "call_prepared": True
            },
            {
                "error": errors.TooManyArguments(),
                "call_prepared": True
            },
            {
                "error": errors.BadArgument(),
                "call_prepared": True
            },
            {
                "error": errors.BadUnionArgument(MagicMock(), MagicMock(), MagicMock()),
                "call_prepared": True
            },
            {
                "error": errors.ArgumentParsingError(),
                "call_prepared": False
            },
            {
                "error": errors.UserInputError(),
                "call_prepared": True
            }
        )

        for case in test_cases:
            with self.subTest(error=case["error"], call_prepared=case["call_prepared"]):
                self.ctx.reset_mock()
                self.assertIsNone(await self.cog.handle_user_input_error(self.ctx, case["error"]))
                self.ctx.send.assert_awaited_once()
                if case["call_prepared"]:
                    self.ctx.send_help.assert_awaited_once()
                else:
                    self.ctx.send_help.assert_not_awaited()

    async def test_handle_check_failure_errors(self):
        """Should await `ctx.send` when error is check failure."""
        test_cases = (
            {
                "error": errors.BotMissingPermissions(MagicMock()),
                "call_ctx_send": True
            },
            {
                "error": errors.BotMissingRole(MagicMock()),
                "call_ctx_send": True
            },
            {
                "error": errors.BotMissingAnyRole(MagicMock()),
                "call_ctx_send": True
            },
            {
                "error": errors.NoPrivateMessage(),
                "call_ctx_send": True
            },
            {
                "error": InWhitelistCheckFailure(1234),
                "call_ctx_send": True
            },
            {
                "error": ResponseCodeError(MagicMock()),
                "call_ctx_send": False
            }
        )

        for case in test_cases:
            with self.subTest(error=case["error"], call_ctx_send=case["call_ctx_send"]):
                self.ctx.reset_mock()
                await self.cog.handle_check_failure(self.ctx, case["error"])
                if case["call_ctx_send"]:
                    self.ctx.send.assert_awaited_once()
                else:
                    self.ctx.send.assert_not_awaited()

    @patch("bot.exts.backend.error_handler.log")
    async def test_handle_api_error(self, log_mock):
        """Should `ctx.send` on HTTP error codes, `log.debug|warning` depends on code."""
        test_cases = (
            {
                "error": ResponseCodeError(AsyncMock(status=400)),
                "log_level": "debug"
            },
            {
                "error": ResponseCodeError(AsyncMock(status=404)),
                "log_level": "debug"
            },
            {
                "error": ResponseCodeError(AsyncMock(status=550)),
                "log_level": "warning"
            },
            {
                "error": ResponseCodeError(AsyncMock(status=1000)),
                "log_level": "warning"
            }
        )

        for case in test_cases:
            with self.subTest(error=case["error"], log_level=case["log_level"]):
                self.ctx.reset_mock()
                log_mock.reset_mock()
                await self.cog.handle_api_error(self.ctx, case["error"])
                self.ctx.send.assert_awaited_once()
                if case["log_level"] == "warning":
                    log_mock.warning.assert_called_once()
                else:
                    log_mock.debug.assert_called_once()

    @patch("bot.exts.backend.error_handler.push_scope")
    @patch("bot.exts.backend.error_handler.log")
    async def test_handle_unexpected_error(self, log_mock, push_scope_mock):
        """Should `ctx.send` this error, error log this and sent to Sentry."""
        for case in (None, MockGuild()):
            with self.subTest(guild=case):
                self.ctx.reset_mock()
                log_mock.reset_mock()
                push_scope_mock.reset_mock()

                self.ctx.guild = case
                await self.cog.handle_unexpected_error(self.ctx, errors.CommandError())

                self.ctx.send.assert_awaited_once()
                log_mock.error.assert_called_once()
                push_scope_mock.assert_called_once()

                set_tag_calls = [
                    call("command", self.ctx.command.qualified_name),
                    call("message_id", self.ctx.message.id),
                    call("channel_id", self.ctx.channel.id),
                ]
                set_extra_calls = [
                    call("full_message", self.ctx.message.content)
                ]
                if case:
                    url = (
                        f"https://discordapp.com/channels/"
                        f"{self.ctx.guild.id}/{self.ctx.channel.id}/{self.ctx.message.id}"
                    )
                    set_extra_calls.append(call("jump_to", url))

                push_scope_mock.set_tag.has_calls(set_tag_calls)
                push_scope_mock.set_extra.has_calls(set_extra_calls)


class OtherErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Other `ErrorHandler` tests."""

    def setUp(self):
        self.bot = MockBot()
        self.ctx = MockContext()

    async def test_get_help_command_command_specified(self):
        """Should return coroutine of help command of specified command."""
        self.ctx.command = "foo"
        result = ErrorHandler.get_help_command(self.ctx)
        expected = self.ctx.send_help("foo")
        self.assertEqual(result.__qualname__, expected.__qualname__)
        self.assertEqual(result.cr_frame.f_locals, expected.cr_frame.f_locals)

        # Await coroutines to avoid warnings
        await result
        await expected

    async def test_get_help_command_no_command_specified(self):
        """Should return coroutine of help command."""
        self.ctx.command = None
        result = ErrorHandler.get_help_command(self.ctx)
        expected = self.ctx.send_help()
        self.assertEqual(result.__qualname__, expected.__qualname__)
        self.assertEqual(result.cr_frame.f_locals, expected.cr_frame.f_locals)

        # Await coroutines to avoid warnings
        await result
        await expected


class ErrorHandlerSetupTests(unittest.TestCase):
    """Tests for `ErrorHandler` `setup` function."""

    def test_setup(self):
        """Should call `bot.add_cog` with `ErrorHandler`."""
        bot = MockBot()
        setup(bot)
        bot.add_cog.assert_called_once()
