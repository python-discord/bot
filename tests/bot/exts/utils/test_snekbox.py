import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, call, create_autospec, patch

from discord.ext import commands

from bot import constants
from bot.exts.utils import snekbox
from bot.exts.utils.snekbox import Snekbox
from tests.helpers import MockBot, MockContext, MockMessage, MockReaction, MockUser


class SnekboxTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        """Add mocked bot and cog to the instance."""
        self.bot = MockBot()
        self.cog = Snekbox(bot=self.bot)

    async def test_post_eval(self):
        """Post the eval code to the URLs.snekbox_eval_api endpoint."""
        resp = MagicMock()
        resp.json = AsyncMock(return_value="return")

        context_manager = MagicMock()
        context_manager.__aenter__.return_value = resp
        self.bot.http_session.post.return_value = context_manager

        self.assertEqual(await self.cog.post_eval("import random"), "return")
        self.bot.http_session.post.assert_called_with(
            constants.URLs.snekbox_eval_api,
            json={"input": "import random"},
            raise_for_status=True
        )
        resp.json.assert_awaited_once()

    async def test_upload_output_reject_too_long(self):
        """Reject output longer than MAX_PASTE_LEN."""
        result = await self.cog.upload_output("-" * (snekbox.MAX_PASTE_LEN + 1))
        self.assertEqual(result, "too long to upload")

    @patch("bot.exts.utils.snekbox.send_to_paste_service")
    async def test_upload_output(self, mock_paste_util):
        """Upload the eval output to the URLs.paste_service.format(key="documents") endpoint."""
        await self.cog.upload_output("Test output.")
        mock_paste_util.assert_called_once_with("Test output.", extension="txt")

    def test_prepare_input(self):
        cases = (
            ('print("Hello world!")', 'print("Hello world!")', 'non-formatted'),
            ('`print("Hello world!")`', 'print("Hello world!")', 'one line code block'),
            ('```\nprint("Hello world!")```', 'print("Hello world!")', 'multiline code block'),
            ('```py\nprint("Hello world!")```', 'print("Hello world!")', 'multiline python code block'),
            ('text```print("Hello world!")```text', 'print("Hello world!")', 'code block surrounded by text'),
            ('```print("Hello world!")```\ntext\n```py\nprint("Hello world!")```',
             'print("Hello world!")\nprint("Hello world!")', 'two code blocks with text in-between'),
            ('`print("Hello world!")`\ntext\n```print("How\'s it going?")```',
             'print("How\'s it going?")', 'code block preceded by inline code'),
            ('`print("Hello world!")`\ntext\n`print("Hello world!")`',
             'print("Hello world!")', 'one inline code block of two')
        )
        for case, expected, testname in cases:
            with self.subTest(msg=f'Extract code from {testname}.'):
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
                actual = self.cog.get_results_message({'stdout': stdout, 'returncode': returncode})
                self.assertEqual(actual, expected)

    @patch('bot.exts.utils.snekbox.Signals', side_effect=ValueError)
    def test_get_results_message_invalid_signal(self, mock_signals: Mock):
        self.assertEqual(
            self.cog.get_results_message({'stdout': '', 'returncode': 127}),
            ('Your eval job has completed with return code 127', '')
        )

    @patch('bot.exts.utils.snekbox.Signals')
    def test_get_results_message_valid_signal(self, mock_signals: Mock):
        mock_signals.return_value.name = 'SIGTEST'
        self.assertEqual(
            self.cog.get_results_message({'stdout': '', 'returncode': 127}),
            ('Your eval job has completed with return code 127 (SIGTEST)', '')
        )

    def test_get_status_emoji(self):
        """Return emoji according to the eval result."""
        cases = (
            (' ', -1, ':warning:'),
            ('Hello world!', 0, ':white_check_mark:'),
            ('Invalid beard size', -1, ':x:')
        )
        for stdout, returncode, expected in cases:
            with self.subTest(stdout=stdout, returncode=returncode, expected=expected):
                actual = self.cog.get_status_emoji({'stdout': stdout, 'returncode': returncode})
                self.assertEqual(actual, expected)

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
                ('Code block escape attempt detected; will not output result', 'https://testificate.com/'),
                'Detect RIGHT-TO-LEFT OVERRIDE'
            ),
            (
                '\u200B\u200B\u200B',
                ('Code block escape attempt detected; will not output result', 'https://testificate.com/'),
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

    async def test_eval_command_evaluate_once(self):
        """Test the eval command procedure."""
        ctx = MockContext()
        response = MockMessage()
        self.cog.prepare_input = MagicMock(return_value='MyAwesomeFormattedCode')
        self.cog.send_eval = AsyncMock(return_value=response)
        self.cog.continue_eval = AsyncMock(return_value=None)

        await self.cog.eval_command(self.cog, ctx=ctx, code='MyAwesomeCode')
        self.cog.prepare_input.assert_called_once_with('MyAwesomeCode')
        self.cog.send_eval.assert_called_once_with(ctx, 'MyAwesomeFormattedCode')
        self.cog.continue_eval.assert_called_once_with(ctx, response)

    async def test_eval_command_evaluate_twice(self):
        """Test the eval and re-eval command procedure."""
        ctx = MockContext()
        response = MockMessage()
        self.cog.prepare_input = MagicMock(return_value='MyAwesomeFormattedCode')
        self.cog.send_eval = AsyncMock(return_value=response)
        self.cog.continue_eval = AsyncMock()
        self.cog.continue_eval.side_effect = ('MyAwesomeCode-2', None)

        await self.cog.eval_command(self.cog, ctx=ctx, code='MyAwesomeCode')
        self.cog.prepare_input.has_calls(call('MyAwesomeCode'), call('MyAwesomeCode-2'))
        self.cog.send_eval.assert_called_with(ctx, 'MyAwesomeFormattedCode')
        self.cog.continue_eval.assert_called_with(ctx, response)

    async def test_eval_command_reject_two_eval_at_the_same_time(self):
        """Test if the eval command rejects an eval if the author already have a running eval."""
        ctx = MockContext()
        ctx.author.id = 42
        ctx.author.mention = '@LemonLemonishBeard#0042'
        ctx.send = AsyncMock()
        self.cog.jobs = (42,)
        await self.cog.eval_command(self.cog, ctx=ctx, code='MyAwesomeCode')
        ctx.send.assert_called_once_with(
            "@LemonLemonishBeard#0042 You've already got a job running - please wait for it to finish!"
        )

    async def test_eval_command_call_help(self):
        """Test if the eval command call the help command if no code is provided."""
        ctx = MockContext(command="sentinel")
        await self.cog.eval_command(self.cog, ctx=ctx, code='')
        ctx.send_help.assert_called_once_with(ctx.command)

    async def test_send_eval(self):
        """Test the send_eval function."""
        ctx = MockContext()
        ctx.message = MockMessage()
        ctx.send = AsyncMock()
        ctx.author.mention = '@LemonLemonishBeard#0042'

        self.cog.post_eval = AsyncMock(return_value={'stdout': '', 'returncode': 0})
        self.cog.get_results_message = MagicMock(return_value=('Return code 0', ''))
        self.cog.get_status_emoji = MagicMock(return_value=':yay!:')
        self.cog.format_output = AsyncMock(return_value=('[No output]', None))

        mocked_filter_cog = MagicMock()
        mocked_filter_cog.filter_eval = AsyncMock(return_value=False)
        self.bot.get_cog.return_value = mocked_filter_cog

        await self.cog.send_eval(ctx, 'MyAwesomeCode')
        ctx.send.assert_called_once_with(
            '@LemonLemonishBeard#0042 :yay!: Return code 0.\n\n```\n[No output]\n```'
        )
        self.cog.post_eval.assert_called_once_with('MyAwesomeCode')
        self.cog.get_status_emoji.assert_called_once_with({'stdout': '', 'returncode': 0})
        self.cog.get_results_message.assert_called_once_with({'stdout': '', 'returncode': 0})
        self.cog.format_output.assert_called_once_with('')

    async def test_send_eval_with_paste_link(self):
        """Test the send_eval function with a too long output that generate a paste link."""
        ctx = MockContext()
        ctx.message = MockMessage()
        ctx.send = AsyncMock()
        ctx.author.mention = '@LemonLemonishBeard#0042'

        self.cog.post_eval = AsyncMock(return_value={'stdout': 'Way too long beard', 'returncode': 0})
        self.cog.get_results_message = MagicMock(return_value=('Return code 0', ''))
        self.cog.get_status_emoji = MagicMock(return_value=':yay!:')
        self.cog.format_output = AsyncMock(return_value=('Way too long beard', 'lookatmybeard.com'))

        mocked_filter_cog = MagicMock()
        mocked_filter_cog.filter_eval = AsyncMock(return_value=False)
        self.bot.get_cog.return_value = mocked_filter_cog

        await self.cog.send_eval(ctx, 'MyAwesomeCode')
        ctx.send.assert_called_once_with(
            '@LemonLemonishBeard#0042 :yay!: Return code 0.'
            '\n\n```\nWay too long beard\n```\nFull output: lookatmybeard.com'
        )
        self.cog.post_eval.assert_called_once_with('MyAwesomeCode')
        self.cog.get_status_emoji.assert_called_once_with({'stdout': 'Way too long beard', 'returncode': 0})
        self.cog.get_results_message.assert_called_once_with({'stdout': 'Way too long beard', 'returncode': 0})
        self.cog.format_output.assert_called_once_with('Way too long beard')

    async def test_send_eval_with_non_zero_eval(self):
        """Test the send_eval function with a code returning a non-zero code."""
        ctx = MockContext()
        ctx.message = MockMessage()
        ctx.send = AsyncMock()
        ctx.author.mention = '@LemonLemonishBeard#0042'
        self.cog.post_eval = AsyncMock(return_value={'stdout': 'ERROR', 'returncode': 127})
        self.cog.get_results_message = MagicMock(return_value=('Return code 127', 'Beard got stuck in the eval'))
        self.cog.get_status_emoji = MagicMock(return_value=':nope!:')
        self.cog.format_output = AsyncMock()  # This function isn't called

        mocked_filter_cog = MagicMock()
        mocked_filter_cog.filter_eval = AsyncMock(return_value=False)
        self.bot.get_cog.return_value = mocked_filter_cog

        await self.cog.send_eval(ctx, 'MyAwesomeCode')
        ctx.send.assert_called_once_with(
            '@LemonLemonishBeard#0042 :nope!: Return code 127.\n\n```\nBeard got stuck in the eval\n```'
        )
        self.cog.post_eval.assert_called_once_with('MyAwesomeCode')
        self.cog.get_status_emoji.assert_called_once_with({'stdout': 'ERROR', 'returncode': 127})
        self.cog.get_results_message.assert_called_once_with({'stdout': 'ERROR', 'returncode': 127})
        self.cog.format_output.assert_not_called()

    @patch("bot.exts.utils.snekbox.partial")
    async def test_continue_eval_does_continue(self, partial_mock):
        """Test that the continue_eval function does continue if required conditions are met."""
        ctx = MockContext(message=MockMessage(add_reaction=AsyncMock(), clear_reactions=AsyncMock()))
        response = MockMessage(delete=AsyncMock())
        new_msg = MockMessage()
        self.bot.wait_for.side_effect = ((None, new_msg), None)
        expected = "NewCode"
        self.cog.get_code = create_autospec(self.cog.get_code, spec_set=True, return_value=expected)

        actual = await self.cog.continue_eval(ctx, response)
        self.cog.get_code.assert_awaited_once_with(new_msg)
        self.assertEqual(actual, expected)
        self.bot.wait_for.assert_has_awaits(
            (
                call(
                    'message_edit',
                    check=partial_mock(snekbox.predicate_eval_message_edit, ctx),
                    timeout=snekbox.REEVAL_TIMEOUT,
                ),
                call('reaction_add', check=partial_mock(snekbox.predicate_eval_emoji_reaction, ctx), timeout=10)
            )
        )
        ctx.message.add_reaction.assert_called_once_with(snekbox.REEVAL_EMOJI)
        ctx.message.clear_reaction.assert_called_once_with(snekbox.REEVAL_EMOJI)
        response.delete.assert_called_once()

    async def test_continue_eval_does_not_continue(self):
        ctx = MockContext(message=MockMessage(clear_reactions=AsyncMock()))
        self.bot.wait_for.side_effect = asyncio.TimeoutError

        actual = await self.cog.continue_eval(ctx, MockMessage())
        self.assertEqual(actual, None)
        ctx.message.clear_reaction.assert_called_once_with(snekbox.REEVAL_EMOJI)

    async def test_get_code(self):
        """Should return 1st arg (or None) if eval cmd in message, otherwise return full content."""
        prefix = constants.Bot.prefix
        subtests = (
            (self.cog.eval_command, f"{prefix}{self.cog.eval_command.name} print(1)", "print(1)"),
            (self.cog.eval_command, f"{prefix}{self.cog.eval_command.name}", None),
            (MagicMock(spec=commands.Command), f"{prefix}tags get foo"),
            (None, "print(123)")
        )

        for command, content, *expected_code in subtests:
            if not expected_code:
                expected_code = content
            else:
                [expected_code] = expected_code

            with self.subTest(content=content, expected_code=expected_code):
                self.bot.get_context.reset_mock()
                self.bot.get_context.return_value = MockContext(command=command)
                message = MockMessage(content=content)

                actual_code = await self.cog.get_code(message)

                self.bot.get_context.assert_awaited_once_with(message)
                self.assertEqual(actual_code, expected_code)

    def test_predicate_eval_message_edit(self):
        """Test the predicate_eval_message_edit function."""
        msg0 = MockMessage(id=1, content='abc')
        msg1 = MockMessage(id=2, content='abcdef')
        msg2 = MockMessage(id=1, content='abcdef')

        cases = (
            (msg0, msg0, False, 'same ID, same content'),
            (msg0, msg1, False, 'different ID, different content'),
            (msg0, msg2, True, 'same ID, different content')
        )
        for ctx_msg, new_msg, expected, testname in cases:
            with self.subTest(msg=f'Messages with {testname} return {expected}'):
                ctx = MockContext(message=ctx_msg)
                actual = snekbox.predicate_eval_message_edit(ctx, ctx_msg, new_msg)
                self.assertEqual(actual, expected)

    def test_predicate_eval_emoji_reaction(self):
        """Test the predicate_eval_emoji_reaction function."""
        valid_reaction = MockReaction(message=MockMessage(id=1))
        valid_reaction.__str__.return_value = snekbox.REEVAL_EMOJI
        valid_ctx = MockContext(message=MockMessage(id=1), author=MockUser(id=2))
        valid_user = MockUser(id=2)

        invalid_reaction_id = MockReaction(message=MockMessage(id=42))
        invalid_reaction_id.__str__.return_value = snekbox.REEVAL_EMOJI
        invalid_user_id = MockUser(id=42)
        invalid_reaction_str = MockReaction(message=MockMessage(id=1))
        invalid_reaction_str.__str__.return_value = ':longbeard:'

        cases = (
            (invalid_reaction_id, valid_user, False, 'invalid reaction ID'),
            (valid_reaction, invalid_user_id, False, 'invalid user ID'),
            (invalid_reaction_str, valid_user, False, 'invalid reaction __str__'),
            (valid_reaction, valid_user, True, 'matching attributes')
        )
        for reaction, user, expected, testname in cases:
            with self.subTest(msg=f'Test with {testname} and expected return {expected}'):
                actual = snekbox.predicate_eval_emoji_reaction(valid_ctx, reaction, user)
                self.assertEqual(actual, expected)


class SnekboxSetupTests(unittest.TestCase):
    """Tests setup of the `Snekbox` cog."""

    def test_setup(self):
        """Setup of the extension should call add_cog."""
        bot = MockBot()
        snekbox.setup(bot)
        bot.add_cog.assert_called_once()
