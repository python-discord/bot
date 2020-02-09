import asyncio
import logging
import unittest
from unittest.mock import MagicMock, Mock, call, patch

from bot.cogs import snekbox
from bot.cogs.snekbox import Snekbox
from bot.constants import URLs
from tests.helpers import (
    AsyncContextManagerMock, AsyncMock, MockBot, MockContext, MockMessage, MockReaction, MockUser, async_test
)


class SnekboxTests(unittest.TestCase):
    def setUp(self):
        """Add mocked bot and cog to the instance."""
        self.bot = MockBot()

        self.mocked_post = MagicMock()
        self.mocked_post.json = AsyncMock()
        self.bot.http_session.post = MagicMock(return_value=AsyncContextManagerMock(self.mocked_post))

        self.cog = Snekbox(bot=self.bot)

    @async_test
    async def test_post_eval(self):
        """Post the eval code to the URLs.snekbox_eval_api endpoint."""
        await self.cog.post_eval("import random")
        self.bot.http_session.post.assert_called_once_with(
            URLs.snekbox_eval_api,
            json={"input": "import random"},
            raise_for_status=True
        )

    @async_test
    async def test_upload_output_reject_too_long(self):
        """Reject output longer than MAX_PASTE_LEN."""
        self.assertEqual(await self.cog.upload_output("-" * (snekbox.MAX_PASTE_LEN + 1)), "too long to upload")

    @async_test
    async def test_upload_output(self):
        """Upload the eval output to the URLs.paste_service.format(key="documents") endpoint."""
        key = "RainbowDash"
        self.mocked_post.json.return_value = {"key": key}

        self.assertEqual(
            await self.cog.upload_output("My awesome output"),
            URLs.paste_service.format(key=key)
        )
        self.bot.http_session.post.assert_called_once_with(
            URLs.paste_service.format(key="documents"),
            data="My awesome output",
            raise_for_status=True
        )

    @async_test
    async def test_upload_output_gracefully_fallback_if_exception_during_request(self):
        """Output upload gracefully fallback if the upload fail."""
        self.mocked_post.json.side_effect = Exception
        log = logging.getLogger("bot.cogs.snekbox")
        with self.assertLogs(logger=log, level='ERROR'):
            await self.cog.upload_output('My awesome output!')

    @async_test
    async def test_upload_output_gracefully_fallback_if_no_key_in_response(self):
        """Output upload gracefully fallback if there is no key entry in the response body."""
        self.mocked_post.json.return_value = {}
        self.assertEqual((await self.cog.upload_output('My awesome output!')), None)

    def test_prepare_input(self):
        cases = (
            ('print("Hello world!")', 'print("Hello world!")', 'non-formatted'),
            ('`print("Hello world!")`', 'print("Hello world!")', 'one line code block'),
            ('```\nprint("Hello world!")```', 'print("Hello world!")', 'multiline code block'),
            ('```py\nprint("Hello world!")```', 'print("Hello world!")', 'multiline python code block'),
        )
        for case, expected, testname in cases:
            with self.subTest(msg=f'Extract code from {testname}.', case=case, expected=expected):
                self.assertEqual(self.cog.prepare_input(case), expected)

    def test_get_results_message(self):
        """Return error and message according to the eval result."""
        cases = (
            ('ERROR', None, ('Your eval job has failed', 'ERROR')),
            ('', 128 + snekbox.SIGKILL, ('Your eval job timed out or ran out of memory', '')),
            ('', 255, ('Your eval job has failed', 'A fatal NsJail error occurred'))
        )
        for stdout, returncode, expected in cases:
            with self.subTest(stdout=stdout, returncode=returncode, expected=expected):
                self.assertEqual(self.cog.get_results_message({'stdout': stdout, 'returncode': returncode}), expected)

    @patch('bot.cogs.snekbox.Signals', side_effect=ValueError)
    def test_get_results_message_invalid_signal(self, mock_Signals: Mock):
        self.assertEqual(
            self.cog.get_results_message({'stdout': '', 'returncode': 127}),
            ('Your eval job has completed with return code 127', '')
        )

    @patch('bot.cogs.snekbox.Signals')
    def test_get_results_message_valid_signal(self, mock_Signals: Mock):
        mock_Signals.return_value.name = 'SIGTEST'
        self.assertEqual(
            self.cog.get_results_message({'stdout': '', 'returncode': 127}),
            ('Your eval job has completed with return code 127 (SIGTEST)', '')
        )

    def test_get_status_emoji(self):
        """Return emoji according to the eval result."""
        cases = (
            ('', -1, ':warning:'),
            ('Hello world!', 0, ':white_check_mark:'),
            ('Invalid beard size', -1, ':x:')
        )
        for stdout, returncode, expected in cases:
            with self.subTest(stdout=stdout, returncode=returncode, expected=expected):
                self.assertEqual(self.cog.get_status_emoji({'stdout': stdout, 'returncode': returncode}), expected)

    @async_test
    async def test_format_output(self):
        """Test output formatting."""
        self.cog.upload_output = AsyncMock(return_value='https://testificate.com/')

        too_many_lines = (
            '001 | v\n002 | e\n003 | r\n004 | y\n005 | l\n006 | o\n'
            '007 | n\n008 | g\n009 | b\n010 | e\n011 | a\n... (truncated - too many lines)'
        )
        too_long_too_many_lines = (
            "\n".join(
                f"{i:03d} | {line}" for i, line in enumerate(['verylongbeard' * 10] * 15, 1)
            )[:1000] + "\n... (truncated - too long, too many lines)"
        )

        cases = (
            ('', ('[No output]', None), 'No output'),
            ('My awesome output', ('My awesome output', None), 'One line output'),
            ('<@', ("<@\u200B", None), r'Convert <@ to <@\u200B'),
            ('<!@', ("<!@\u200B", None), r'Convert <!@ to <!@\u200B'),
            (
                '\u202E\u202E\u202E',
                ('Code block escape attempt detected; will not output result', None),
                'Detect RIGHT-TO-LEFT OVERRIDE'
            ),
            (
                '\u200B\u200B\u200B',
                ('Code block escape attempt detected; will not output result', None),
                'Detect ZERO WIDTH SPACE'
            ),
            ('long\nbeard', ('001 | long\n002 | beard', None), 'Two line output'),
            (
                'v\ne\nr\ny\nl\no\nn\ng\nb\ne\na\nr\nd',
                (too_many_lines, 'https://testificate.com/'),
                '12 lines output'
            ),
            (
                'verylongbeard' * 100,
                ('verylongbeard' * 76 + 'verylongbear\n... (truncated - too long)', 'https://testificate.com/'),
                '1300 characters output'
            ),
            (
                ('verylongbeard' * 10 + '\n') * 15,
                (too_long_too_many_lines, 'https://testificate.com/'),
                '15 lines, 1965 characters output'
            ),
        )
        for case, expected, testname in cases:
            with self.subTest(msg=testname, case=case, expected=expected):
                self.assertEqual(await self.cog.format_output(case), expected)

    @async_test
    async def test_eval_command_evaluate_once(self):
        """Test the eval command procedure."""
        ctx = MockContext()
        ctx.message = MockMessage()
        ctx.send = AsyncMock()
        ctx.author.mention = '@LemonLemonishBeard#0042'
        ctx.typing = MagicMock(return_value=AsyncContextManagerMock(None))
        self.cog.post_eval = AsyncMock(return_value={'stdout': '', 'returncode': 0})
        self.cog.get_results_message = MagicMock(return_value=('Return code 0', ''))
        self.cog.get_status_emoji = MagicMock(return_value=':yay!:')
        self.cog.format_output = AsyncMock(return_value=('[No output]', None))
        self.bot.wait_for.side_effect = asyncio.TimeoutError

        await self.cog.eval_command.callback(self.cog, ctx=ctx, code='MyAwesomeCode')

        ctx.send.assert_called_once_with(
            '@LemonLemonishBeard#0042 :yay!: Return code 0.\n\n```py\n[No output]\n```'
        )
        self.cog.post_eval.assert_called_once_with('MyAwesomeCode')
        self.cog.get_status_emoji.assert_called_once_with({'stdout': '', 'returncode': 0})
        self.cog.get_results_message.assert_called_once_with({'stdout': '', 'returncode': 0})
        self.cog.format_output.assert_called_once_with('')

    @async_test
    async def test_eval_command_reject_two_eval(self):
        """Test if the eval command rejects an eval if the author already have a running eval."""
        ctx = MockContext()
        ctx.author.id = 42
        ctx.author.mention = '@LemonLemonishBeard#0042'
        ctx.send = AsyncMock()
        self.cog.jobs = (42,)
        await self.cog.eval_command.callback(self.cog, ctx=ctx, code='MyAwesomeCode')
        ctx.send.assert_called_once_with(
            "@LemonLemonishBeard#0042 You've already got a job running - please wait for it to finish!"
        )

    @async_test
    async def test_eval_command_call_help(self):
        """Test if the eval command call the help command if no code is provided."""
        ctx = MockContext()
        ctx.invoke = AsyncMock()
        await self.cog.eval_command.callback(self.cog, ctx=ctx, code='')
        ctx.invoke.assert_called_once_with(self.bot.get_command("help"), "eval")

    @async_test
    async def test_eval_command_return_error(self):
        """Test the eval command error handling."""
        ctx = MockContext()
        ctx.message = MockMessage()
        ctx.send = AsyncMock()
        ctx.author.mention = '@LemonLemonishBeard#0042'
        ctx.typing = MagicMock(return_value=AsyncContextManagerMock(None))
        self.cog.post_eval = AsyncMock(return_value={'stdout': 'ERROR', 'returncode': 127})
        self.cog.get_results_message = MagicMock(return_value=('Return code 127', 'Error occurred'))
        self.cog.get_status_emoji = MagicMock(return_value=':nope!:')
        self.cog.format_output = AsyncMock()
        self.bot.wait_for.side_effect = asyncio.TimeoutError

        await self.cog.eval_command.callback(self.cog, ctx=ctx, code='MyAwesomeCode')

        ctx.send.assert_called_once_with(
            '@LemonLemonishBeard#0042 :nope!: Return code 127.\n\n```py\nError occurred\n```'
        )
        self.cog.post_eval.assert_called_once_with('MyAwesomeCode')
        self.cog.get_results_message.assert_called_once_with({'stdout': 'ERROR', 'returncode': 127})
        self.cog.get_status_emoji.assert_called_once_with({'stdout': 'ERROR', 'returncode': 127})
        self.cog.format_output.assert_not_called()

    @async_test
    async def test_eval_command_with_paste_link(self):
        """Test the eval command procedure with the use of a paste link."""
        ctx = MockContext()
        ctx.message = MockMessage()
        ctx.send = AsyncMock()
        ctx.author.mention = '@LemonLemonishBeard#0042'
        ctx.typing = MagicMock(return_value=AsyncContextManagerMock(None))
        self.cog.post_eval = AsyncMock(return_value={'stdout': 'SuperLongBeard', 'returncode': 0})
        self.cog.get_results_message = MagicMock(return_value=('Return code 0', ''))
        self.cog.get_status_emoji = MagicMock(return_value=':yay!:')
        self.cog.format_output = AsyncMock(return_value=('Truncated - too long beard', 'https://testificate.com/'))
        self.bot.wait_for.side_effect = asyncio.TimeoutError

        await self.cog.eval_command.callback(self.cog, ctx=ctx, code='MyAwesomeCode')

        ctx.send.assert_called_once_with(
            '@LemonLemonishBeard#0042 :yay!: Return code 0.\n\n```py\n'
            'Truncated - too long beard\n```\nFull output: https://testificate.com/'
        )
        self.cog.post_eval.assert_called_once_with('MyAwesomeCode')
        self.cog.get_status_emoji.assert_called_once_with({'stdout': 'SuperLongBeard', 'returncode': 0})
        self.cog.get_results_message.assert_called_once_with({'stdout': 'SuperLongBeard', 'returncode': 0})
        self.cog.format_output.assert_called_with('SuperLongBeard')

    @async_test
    async def test_eval_command_evaluate_twice(self):
        """Test the eval command re-evaluation procedure."""
        ctx = MockContext()
        ctx.message = MockMessage()
        ctx.message.content = '!e MyAwesomeCode'
        updated_msg = MockMessage()
        updated_msg .content = '!e MyAwesomeCode-2'
        response_msg = MockMessage()
        response_msg.delete = AsyncMock()
        ctx.send = AsyncMock(return_value=response_msg)
        ctx.author.mention = '@LemonLemonishBeard#0042'
        ctx.typing = MagicMock(return_value=AsyncContextManagerMock(None))
        self.cog.post_eval = AsyncMock(return_value={'stdout': '', 'returncode': 0})
        self.cog.get_results_message = MagicMock(return_value=('Return code 0', ''))
        self.cog.get_status_emoji = MagicMock(return_value=':yay!:')
        self.cog.format_output = AsyncMock(return_value=('[No output]', None))
        self.bot.wait_for.side_effect = ((None, updated_msg), None, asyncio.TimeoutError)

        await self.cog.eval_command.callback(self.cog, ctx=ctx, code='MyAwesomeCode')

        self.cog.post_eval.assert_has_calls((call('MyAwesomeCode'), call('MyAwesomeCode-2')))

        # Multiplied by 2 because we expect it to be called twice
        ctx.send.assert_has_calls(
            [call('@LemonLemonishBeard#0042 :yay!: Return code 0.\n\n```py\n[No output]\n```')] * 2
        )
        self.cog.get_status_emoji.assert_has_calls([call({'stdout': '', 'returncode': 0})] * 2)
        self.cog.get_results_message.assert_has_calls([call({'stdout': '', 'returncode': 0})] * 2)
        self.cog.format_output.assert_has_calls([call('')] * 2)

        self.bot.wait_for.has_calls(
            call('message_edit', check=snekbox.predicate_eval_message_edit, timeout=10),
            call('reaction_add', check=snekbox.predicate_eval_emoji_reaction, timeout=10)
        )
        ctx.message.add_reaction.assert_called_once_with('🔁')
        ctx.message.clear_reactions.assert_called()
        response_msg.delete.assert_called_once()

    def test_predicate_eval_message_edit(self):
        """Test the predicate_eval_message_edit function."""
        msg0 = MockMessage()
        msg0.id = 1
        msg0.content = 'abc'
        msg1 = MockMessage()
        msg1.id = 2
        msg1.content = 'abcdef'
        msg2 = MockMessage()
        msg2.id = 1
        msg2.content = 'abcdef'

        cases = (
            (msg0, msg0, False, 'same ID, same content'),
            (msg0, msg1, False, 'different ID, different content'),
            (msg0, msg2, True, 'same ID, different content')
        )
        for ctx_msg, new_msg, expected, testname in cases:
            with self.subTest(msg=f'Messages with {testname} return {expected}'):
                ctx = MockContext()
                ctx.message = ctx_msg
                self.assertEqual(snekbox.predicate_eval_message_edit(ctx, ctx_msg, new_msg), expected)

    def test_predicate_eval_emoji_reaction(self):
        """Test the predicate_eval_emoji_reaction function."""
        valid_reaction = MockReaction()
        valid_reaction.message.id = 1
        valid_reaction.__str__.return_value = '🔁'
        valid_ctx = MockContext()
        valid_ctx.message.id = 1
        valid_ctx.author.id = 2
        valid_user = MockUser()
        valid_user.id = 2

        invalid_reaction_id = MockReaction()
        invalid_reaction_id.message.id = 42
        invalid_reaction_id.__str__.return_value = '🔁'
        invalid_user_id = MockUser()
        invalid_user_id.id = 42
        invalid_reaction_str = MockReaction()
        invalid_reaction_str.message.id = 1
        invalid_reaction_str.__str__.return_value = ':longbeard:'

        cases = (
            (invalid_reaction_id, valid_user, False, 'invalid reaction ID'),
            (valid_reaction, invalid_user_id, False, 'invalid user ID'),
            (invalid_reaction_str, valid_user, False, 'invalid reaction __str__'),
            (valid_reaction, valid_user, True, 'matching attributes')
        )
        for reaction, user, expected, testname in cases:
            with self.subTest(msg=f'Test with {testname} and expected return {expected}'):
                self.assertEqual(snekbox.predicate_eval_emoji_reaction(valid_ctx, reaction, user), expected)


class SnekboxSetupTests(unittest.TestCase):
    """Tests setup of the `Snekbox` cog."""

    def test_setup(self):
        """Setup of the extension should call add_cog."""
        bot = MockBot()
        snekbox.setup(bot)
        bot.add_cog.assert_called_once()
