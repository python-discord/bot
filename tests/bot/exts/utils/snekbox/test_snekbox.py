import asyncio
import unittest
from base64 import b64encode
from unittest.mock import AsyncMock, MagicMock, Mock, call, create_autospec, patch

from discord import AllowedMentions
from discord.ext import commands
from pydis_core.utils.paste_service import MAX_PASTE_SIZE

from bot import constants
from bot.errors import LockedResourceError
from bot.exts.utils import snekbox
from bot.exts.utils.snekbox import EvalJob, EvalResult, Snekbox
from bot.exts.utils.snekbox._io import FileAttachment
from tests.helpers import MockBot, MockContext, MockMember, MockMessage, MockReaction, MockUser


class SnekboxTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        """Add mocked bot and cog to the instance."""
        self.bot = MockBot()
        self.cog = Snekbox(bot=self.bot)
        self.job = EvalJob.from_code("import random")

    @staticmethod
    def code_args(code: str) -> tuple[EvalJob]:
        """Converts code to a tuple of arguments expected."""
        return EvalJob.from_code(code),

    async def test_post_job(self):
        """Post the eval code to the URLs.snekbox_eval_api endpoint."""
        resp = MagicMock()
        resp.json = AsyncMock(return_value={"stdout": "Hi", "returncode": 137, "files": []})

        context_manager = MagicMock()
        context_manager.__aenter__.return_value = resp
        self.bot.http_session.post.return_value = context_manager

        job = EvalJob.from_code("import random").as_version("3.10")
        self.assertEqual(await self.cog.post_job(job), EvalResult("Hi", 137))

        expected = {
            "args": ["main.py"],
            "files": [
                {
                    "path": "main.py",
                    "content": b64encode(b"import random").decode()
                }
            ]
        }
        self.bot.http_session.post.assert_called_with(
            constants.URLs.snekbox_eval_api,
            json=expected,
            raise_for_status=True
        )
        resp.json.assert_awaited_once()

    @patch(
        "bot.exts.utils.snekbox._cog.paste_service._lexers_supported_by_pastebin",
        {"https://paste.pythondiscord.com": ["text"]},
    )
    async def test_upload_output_reject_too_long(self):
        """Reject output longer than MAX_PASTE_LENGTH."""
        result = await self.cog.upload_output("-" * (MAX_PASTE_SIZE + 1))
        self.assertEqual(result, "too long to upload")

    async def test_codeblock_converter(self):
        ctx = MockContext()
        cases = (
            ('print("Hello world!")', 'print("Hello world!")', "non-formatted"),
            ('`print("Hello world!")`', 'print("Hello world!")', "one line code block"),
            ('```\nprint("Hello world!")```', 'print("Hello world!")', "multiline code block"),
            ('```py\nprint("Hello world!")```', 'print("Hello world!")', "multiline python code block"),
            ('text```print("Hello world!")```text', 'print("Hello world!")', "code block surrounded by text"),
            ('```print("Hello world!")```\ntext\n```py\nprint("Hello world!")```',
             'print("Hello world!")\nprint("Hello world!")', "two code blocks with text in-between"),
            ('`print("Hello world!")`\ntext\n```print("How\'s it going?")```',
             'print("How\'s it going?")', "code block preceded by inline code"),
            ('`print("Hello world!")`\ntext\n`print("Hello world!")`',
             'print("Hello world!")', "one inline code block of two")
        )
        for case, expected, testname in cases:
            with self.subTest(msg=f"Extract code from {testname}."):
                self.assertEqual(
                    "\n".join(await snekbox.CodeblockConverter.convert(ctx, case)), expected
                )

    def test_prepare_timeit_input(self):
        """Test the prepare_timeit_input codeblock detection."""
        base_args = ("-m", "timeit", "-s")
        cases = (
            (['print("Hello World")'], "", "single block of code"),
            (["x = 1", "print(x)"], "x = 1", "two blocks of code"),
            (["x = 1", "print(x)", 'print("Some other code.")'], "x = 1", "three blocks of code")
        )

        for case, setup_code, test_name in cases:
            setup = snekbox._cog.TIMEIT_SETUP_WRAPPER.format(setup=setup_code)
            expected = [*base_args, setup, "\n".join(case[1:] if setup_code else case)]
            with self.subTest(msg=f"Test with {test_name} and expected return {expected}"):
                self.assertEqual(self.cog.prepare_timeit_input(case), expected)

    def test_eval_result_message(self):
        """EvalResult.get_message(), should return message."""
        cases = (
            ("ERROR", None, ("Your 3.12 eval job has failed", "ERROR", "")),
            ("", 128 + snekbox._eval.SIGKILL, ("Your 3.12 eval job timed out or ran out of memory", "", "")),
            ("", 255, ("Your 3.12 eval job has failed", "A fatal NsJail error occurred", ""))
        )
        for stdout, returncode, expected in cases:
            exp_msg, exp_err, exp_files_err = expected
            with self.subTest(stdout=stdout, returncode=returncode, expected=expected):
                result = EvalResult(stdout=stdout, returncode=returncode)
                job = EvalJob([])
                # Check all 3 message types
                msg = result.get_status_message(job)
                self.assertEqual(msg, exp_msg)
                error = result.error_message
                self.assertEqual(error, exp_err)
                files_error = result.files_error_message
                self.assertEqual(files_error, exp_files_err)

    @patch("bot.exts.utils.snekbox._eval.FILE_COUNT_LIMIT", 2)
    def test_eval_result_files_error_message(self):
        """EvalResult.files_error_message, should return files error message."""
        cases = [
            ([], ["abc"], (
                "1 file upload (abc) failed because its file size exceeds 8 MiB."
            )),
            ([], ["file1.bin", "f2.bin"], (
                "2 file uploads (file1.bin, f2.bin) failed because each file's size exceeds 8 MiB."
            )),
            (["a", "b"], ["c"], (
                "1 file upload (c) failed as it exceeded the 2 file limit."
            )),
            (["a"], ["b", "c"], (
                "2 file uploads (b, c) failed as they exceeded the 2 file limit."
            )),
        ]
        for files, failed_files, expected_msg in cases:
            with self.subTest(files=files, failed_files=failed_files, expected_msg=expected_msg):
                result = EvalResult("", 0, files, failed_files)
                msg = result.files_error_message
                self.assertIn(expected_msg, msg)

    @patch("bot.exts.utils.snekbox._eval.FILE_COUNT_LIMIT", 2)
    def test_eval_result_files_error_str(self):
        """EvalResult.files_error_message, should return files error message."""
        cases = [
            # Normal
            (["x.ini"], "x.ini"),
            (["123456", "879"], "123456, 879"),
            # Break on whole name if less than 3 characters remaining
            (["12345678", "9"], "12345678, ..."),
            # Otherwise break on max chars
            (["123", "345", "67890000"], "123, 345, 6789..."),
            (["abcdefg1234567"], "abcdefg123..."),
        ]
        for failed_files, expected in cases:
            with self.subTest(failed_files=failed_files, expected=expected):
                result = EvalResult("", 0, [], failed_files)
                msg = result.get_failed_files_str(char_max=10)
                self.assertEqual(msg, expected)

    @patch("bot.exts.utils.snekbox._eval.Signals", side_effect=ValueError)
    def test_eval_result_message_invalid_signal(self, _mock_signals: Mock):
        result = EvalResult(stdout="", returncode=127)
        self.assertEqual(
            result.get_status_message(EvalJob([], version="3.10")),
            "Your 3.10 eval job has completed with return code 127"
        )
        self.assertEqual(result.error_message, "")
        self.assertEqual(result.files_error_message, "")

    @patch("bot.exts.utils.snekbox._eval.Signals")
    def test_eval_result_message_valid_signal(self, mock_signals: Mock):
        mock_signals.return_value.name = "SIGTEST"
        result = EvalResult(stdout="", returncode=127)
        self.assertEqual(
            result.get_status_message(EvalJob([], version="3.12")),
            "Your 3.12 eval job has completed with return code 127 (SIGTEST)"
        )

    def test_eval_result_status_emoji(self):
        """Return emoji according to the eval result."""
        cases = (
            (" ", -1, ":warning:"),
            ("Hello world!", 0, ":white_check_mark:"),
            ("Invalid beard size", -1, ":x:")
        )
        for stdout, returncode, expected in cases:
            with self.subTest(stdout=stdout, returncode=returncode, expected=expected):
                result = EvalResult(stdout=stdout, returncode=returncode)
                self.assertEqual(result.status_emoji, expected)

    async def test_format_output(self):
        """Test output formatting."""
        self.cog.upload_output = AsyncMock(return_value="https://testificate.com/")

        too_many_lines = (
            "001 | v\n002 | e\n003 | r\n004 | y\n005 | l\n006 | o\n"
            "007 | n\n008 | g\n009 | b\n010 | e\n... (truncated - too many lines)"
        )
        too_long_too_many_lines = (
            "\n".join(
                f"{i:03d} | {line}" for i, line in enumerate(["verylongbeard" * 10] * 15, 1)
            )[:1000] + "\n... (truncated - too long, too many lines)"
        )

        cases = (
            ("", ("[No output]", None), "No output"),
            ("My awesome output", ("My awesome output", None), "One line output"),
            ("<@", ("<@\u200B", None), r"Convert <@ to <@\u200B"),
            ("<!@", ("<!@\u200B", None), r"Convert <!@ to <!@\u200B"),
            (
                "\u202E\u202E\u202E",
                ("Code block escape attempt detected; will not output result", "https://testificate.com/"),
                "Detect RIGHT-TO-LEFT OVERRIDE"
            ),
            (
                "\u200B\u200B\u200B",
                ("Code block escape attempt detected; will not output result", "https://testificate.com/"),
                "Detect ZERO WIDTH SPACE"
            ),
            ("long\nbeard", ("001 | long\n002 | beard", None), "Two line output"),
            (
                "v\ne\nr\ny\nl\no\nn\ng\nb\ne\na\nr\nd",
                (too_many_lines, "https://testificate.com/"),
                "12 lines output"
            ),
            (
                "verylongbeard" * 100,
                ("verylongbeard" * 76 + "verylongbear\n... (truncated - too long)", "https://testificate.com/"),
                "1300 characters output"
            ),
            (
                ("verylongbeard" * 10 + "\n") * 15,
                (too_long_too_many_lines, "https://testificate.com/"),
                "15 lines, 1965 characters output"
            ),
        )
        for case, expected, testname in cases:
            with self.subTest(msg=testname, case=case, expected=expected):
                self.assertEqual(await self.cog.format_output(case), expected)

    async def test_eval_command_evaluate_once(self):
        """Test the eval command procedure."""
        ctx = MockContext()
        response = MockMessage()
        ctx.command = MagicMock()

        self.cog.send_job = AsyncMock(return_value=response)
        self.cog.continue_job = AsyncMock(return_value=None)

        await self.cog.eval_command(self.cog, ctx=ctx, python_version="3.12", code=["MyAwesomeCode"])
        job = EvalJob.from_code("MyAwesomeCode")
        self.cog.send_job.assert_called_once_with(ctx, job)
        self.cog.continue_job.assert_called_once_with(ctx, response, "eval")

    async def test_eval_command_evaluate_twice(self):
        """Test the eval and re-eval command procedure."""
        ctx = MockContext()
        response = MockMessage()
        ctx.command = MagicMock()
        self.cog.send_job = AsyncMock(return_value=response)
        self.cog.continue_job = AsyncMock()
        self.cog.continue_job.side_effect = (EvalJob.from_code("MyAwesomeFormattedCode"), None)

        await self.cog.eval_command(self.cog, ctx=ctx, python_version="3.12", code=["MyAwesomeCode"])

        expected_job = EvalJob.from_code("MyAwesomeFormattedCode")
        self.cog.send_job.assert_called_with(ctx, expected_job)
        self.cog.continue_job.assert_called_with(ctx, response, "eval")

    async def test_eval_command_reject_two_eval_at_the_same_time(self):
        """Test if the eval command rejects an eval if the author already have a running eval."""
        ctx = MockContext()
        ctx.author.id = 42

        async def delay_with_side_effect(*args, **kwargs) -> dict:
            """Delay the post_job call to ensure the job runs long enough to conflict."""
            await asyncio.sleep(1)
            return {"stdout": "", "returncode": 0}

        self.cog.post_job = AsyncMock(side_effect=delay_with_side_effect)
        with self.assertRaises(LockedResourceError):
            await asyncio.gather(
                self.cog.send_job(ctx, EvalJob.from_code("MyAwesomeCode")),
                self.cog.send_job(ctx, EvalJob.from_code("MyAwesomeCode")),
            )

    async def test_send_job(self):
        """Test the send_job function."""
        ctx = MockContext()
        ctx.send = AsyncMock()
        ctx.author = MockUser(mention="@LemonLemonishBeard#0042")

        eval_result = EvalResult("", 0)
        self.cog.post_job = AsyncMock(return_value=eval_result)
        self.cog.format_output = AsyncMock(return_value=("[No output]", None))
        self.cog.upload_output = AsyncMock()  # Should not be called

        mocked_filter_cog = MagicMock()
        mocked_filter_cog.filter_snekbox_output = AsyncMock(return_value=(False, []))
        self.bot.get_cog.return_value = mocked_filter_cog

        job = EvalJob.from_code("MyAwesomeCode")
        await self.cog.send_job(ctx, job),

        ctx.send.assert_called_once()
        self.assertEqual(
            ctx.send.call_args.args[0],
            ":warning: Your 3.12 eval job has completed "
            "with return code 0.\n\n```\n[No output]\n```"
        )
        allowed_mentions = ctx.send.call_args.kwargs["allowed_mentions"]
        expected_allowed_mentions = AllowedMentions(everyone=False, roles=False, users=[ctx.author])
        self.assertEqual(allowed_mentions.to_dict(), expected_allowed_mentions.to_dict())

        self.cog.post_job.assert_called_once_with(job)
        self.cog.format_output.assert_called_once_with("")
        self.cog.upload_output.assert_not_called()

    async def test_send_job_with_paste_link(self):
        """Test the send_job function with a too long output that generate a paste link."""
        ctx = MockContext()
        ctx.send = AsyncMock()

        eval_result = EvalResult("Way too long beard", 0)
        self.cog.post_job = AsyncMock(return_value=eval_result)
        self.cog.format_output = AsyncMock(return_value=("Way too long beard", "lookatmybeard.com"))

        mocked_filter_cog = MagicMock()
        mocked_filter_cog.filter_snekbox_output = AsyncMock(return_value=(False, []))
        self.bot.get_cog.return_value = mocked_filter_cog

        job = EvalJob.from_code("MyAwesomeCode").as_version("3.12")
        await self.cog.send_job(ctx, job),

        ctx.send.assert_called_once()
        self.assertEqual(
            ctx.send.call_args.args[0],
            ":white_check_mark: Your 3.12 eval job "
            "has completed with return code 0."
            "\n\n```\nWay too long beard\n```\nFull output: lookatmybeard.com"
        )

        self.cog.post_job.assert_called_once_with(job)
        self.cog.format_output.assert_called_once_with("Way too long beard")

    async def test_send_job_with_non_zero_eval(self):
        """Test the send_job function with a code returning a non-zero code."""
        ctx = MockContext()
        ctx.send = AsyncMock()

        eval_result = EvalResult("ERROR", 127)
        self.cog.post_job = AsyncMock(return_value=eval_result)
        self.cog.upload_output = AsyncMock()  # This function isn't called

        mocked_filter_cog = MagicMock()
        mocked_filter_cog.filter_snekbox_output = AsyncMock(return_value=(False, []))
        self.bot.get_cog.return_value = mocked_filter_cog

        job = EvalJob.from_code("MyAwesomeCode").as_version("3.12")
        await self.cog.send_job(ctx, job),

        ctx.send.assert_called_once()
        self.assertEqual(
            ctx.send.call_args.args[0],
            ":x: Your 3.12 eval job has completed with return code 127."
            "\n\n```\nERROR\n```"
        )

        self.cog.post_job.assert_called_once_with(job)
        self.cog.upload_output.assert_not_called()

    async def test_send_job_with_disallowed_file_ext(self):
        """Test send_job with disallowed file extensions."""
        ctx = MockContext()
        ctx.send = AsyncMock()

        files = [
            FileAttachment("test.disallowed2", b"test"),
            FileAttachment("test.disallowed", b"test"),
            FileAttachment("test.allowed", b"test"),
            FileAttachment("test." + ("a" * 100), b"test")
        ]
        eval_result = EvalResult("", 0, files=files)
        self.cog.post_job = AsyncMock(return_value=eval_result)
        self.cog.upload_output = AsyncMock()  # This function isn't called

        disallowed_exts = [".disallowed", "." + ("a" * 100), ".disallowed2"]
        mocked_filter_cog = MagicMock()
        mocked_filter_cog.filter_snekbox_output = AsyncMock(return_value=(False, disallowed_exts))
        self.bot.get_cog.return_value = mocked_filter_cog

        job = EvalJob.from_code("MyAwesomeCode").as_version("3.12")
        await self.cog.send_job(ctx, job),

        ctx.send.assert_called_once()
        res = ctx.send.call_args.args[0]
        self.assertTrue(
            res.startswith(":white_check_mark: Your 3.12 eval job has completed with return code 0.")
        )
        self.assertIn("Files with disallowed extensions can't be uploaded: **.disallowed, .disallowed2, ...**", res)

        self.cog.post_job.assert_called_once_with(job)
        self.cog.upload_output.assert_not_called()

    @patch("bot.exts.utils.snekbox._cog.partial")
    async def test_continue_job_does_continue(self, partial_mock):
        """Test that the continue_job function does continue if required conditions are met."""
        ctx = MockContext(
            message=MockMessage(
                id=4,
                add_reaction=AsyncMock(),
                clear_reactions=AsyncMock()
            ),
            author=MockMember(id=14)
        )
        response = MockMessage(id=42, delete=AsyncMock())
        new_msg = MockMessage()
        self.cog.jobs = {4: 42}
        self.bot.wait_for.side_effect = ((None, new_msg), None)
        expected = "NewCode"
        self.cog.get_code = create_autospec(self.cog.get_code, spec_set=True, return_value=expected)

        actual = await self.cog.continue_job(ctx, response, self.cog.eval_command)
        self.cog.get_code.assert_awaited_once_with(new_msg, ctx.command)
        self.assertEqual(actual, EvalJob.from_code(expected))
        self.bot.wait_for.assert_has_awaits(
            (
                call(
                    "message_edit",
                    check=partial_mock(snekbox._cog.predicate_message_edit, ctx),
                    timeout=snekbox._cog.REDO_TIMEOUT,
                ),
                call("reaction_add", check=partial_mock(snekbox._cog.predicate_emoji_reaction, ctx), timeout=10)
            )
        )
        ctx.message.add_reaction.assert_called_once_with(snekbox._cog.REDO_EMOJI)
        ctx.message.clear_reaction.assert_called_once_with(snekbox._cog.REDO_EMOJI)
        response.delete.assert_called_once()

    async def test_continue_job_does_not_continue(self):
        ctx = MockContext(message=MockMessage(clear_reactions=AsyncMock()))
        self.bot.wait_for.side_effect = asyncio.TimeoutError

        actual = await self.cog.continue_job(ctx, MockMessage(), self.cog.eval_command)
        self.assertEqual(actual, None)
        ctx.message.clear_reaction.assert_called_once_with(snekbox._cog.REDO_EMOJI)

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

                actual_code = await self.cog.get_code(message, self.cog.eval_command)

                self.bot.get_context.assert_awaited_once_with(message)
                self.assertEqual(actual_code, expected_code)

    def test_predicate_message_edit(self):
        """Test the predicate_message_edit function."""
        msg0 = MockMessage(id=1, content="abc")
        msg1 = MockMessage(id=2, content="abcdef")
        msg2 = MockMessage(id=1, content="abcdef")

        cases = (
            (msg0, msg0, False, "same ID, same content"),
            (msg0, msg1, False, "different ID, different content"),
            (msg0, msg2, True, "same ID, different content")
        )
        for ctx_msg, new_msg, expected, testname in cases:
            with self.subTest(msg=f"Messages with {testname} return {expected}"):
                ctx = MockContext(message=ctx_msg)
                actual = snekbox._cog.predicate_message_edit(ctx, ctx_msg, new_msg)
                self.assertEqual(actual, expected)

    def test_predicate_emoji_reaction(self):
        """Test the predicate_emoji_reaction function."""
        valid_reaction = MockReaction(message=MockMessage(id=1))
        valid_reaction.__str__.return_value = snekbox._cog.REDO_EMOJI
        valid_ctx = MockContext(message=MockMessage(id=1), author=MockUser(id=2))
        valid_user = MockUser(id=2)

        invalid_reaction_id = MockReaction(message=MockMessage(id=42))
        invalid_reaction_id.__str__.return_value = snekbox._cog.REDO_EMOJI
        invalid_user_id = MockUser(id=42)
        invalid_reaction_str = MockReaction(message=MockMessage(id=1))
        invalid_reaction_str.__str__.return_value = ":longbeard:"

        cases = (
            (invalid_reaction_id, valid_user, False, "invalid reaction ID"),
            (valid_reaction, invalid_user_id, False, "invalid user ID"),
            (invalid_reaction_str, valid_user, False, "invalid reaction __str__"),
            (valid_reaction, valid_user, True, "matching attributes")
        )
        for reaction, user, expected, testname in cases:
            with self.subTest(msg=f"Test with {testname} and expected return {expected}"):
                actual = snekbox._cog.predicate_emoji_reaction(valid_ctx, reaction, user)
                self.assertEqual(actual, expected)


class SnekboxSetupTests(unittest.IsolatedAsyncioTestCase):
    """Tests setup of the `Snekbox` cog."""

    async def test_setup(self):
        """Setup of the extension should call add_cog."""
        bot = MockBot()
        await snekbox.setup(bot)
        bot.add_cog.assert_awaited_once()
