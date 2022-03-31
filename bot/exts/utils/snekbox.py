import asyncio
import contextlib
import datetime
import re
from functools import partial
from signal import Signals
from textwrap import dedent
from typing import Optional, Tuple

from botcore.regex import FORMATTED_CODE_REGEX, RAW_CODE_REGEX
from discord import AllowedMentions, HTTPException, Message, NotFound, Reaction, User
from discord.ext.commands import Cog, Command, Context, Converter, command, guild_only

from bot.bot import Bot
from bot.constants import Categories, Channels, Roles, URLs
from bot.decorators import redirect_output
from bot.log import get_logger
from bot.utils import scheduling, send_to_paste_service
from bot.utils.messages import wait_for_deletion

log = get_logger(__name__)

ESCAPE_REGEX = re.compile("[`\u202E\u200B]{3,}")

# The timeit command should only output the very last line, so all other output should be suppressed.
# This will be used as the setup code along with any setup code provided.
TIMEIT_SETUP_WRAPPER = """
import atexit
import sys
from collections import deque

if not hasattr(sys, "_setup_finished"):
    class Writer(deque):
        '''A single-item deque wrapper for sys.stdout that will return the last line when read() is called.'''

        def __init__(self):
            super().__init__(maxlen=1)

        def write(self, string):
            '''Append the line to the queue if it is not empty.'''
            if string.strip():
                self.append(string)

        def read(self):
            '''This method will be called when print() is called.

            The queue is emptied as we don't need the output later.
            '''
            return self.pop()

        def flush(self):
            '''This method will be called eventually, but we don't need to do anything here.'''
            pass

    sys.stdout = Writer()

    def print_last_line():
        if sys.stdout: # If the deque is empty (i.e. an error happened), calling read() will raise an error
            # Use sys.__stdout__ here because sys.stdout is set to a Writer() instance
            print(sys.stdout.read(), file=sys.__stdout__)

    atexit.register(print_last_line) # When exiting, print the last line (hopefully it will be the timeit output)
    sys._setup_finished = None
{setup}
"""

MAX_PASTE_LEN = 10000

# The Snekbox commands' whitelists and blacklists.
NO_SNEKBOX_CHANNELS = (Channels.python_general,)
NO_SNEKBOX_CATEGORIES = ()
SNEKBOX_ROLES = (Roles.helpers, Roles.moderators, Roles.admins, Roles.owners, Roles.python_community, Roles.partners)

SIGKILL = 9

REDO_EMOJI = '\U0001f501'  # :repeat:
REDO_TIMEOUT = 30


class CodeblockConverter(Converter):
    """Attempts to extract code from a codeblock, if provided."""

    @classmethod
    async def convert(cls, ctx: Context, code: str) -> list[str]:
        """
        Extract code from the Markdown, format it, and insert it into the code template.

        If there is any code block, ignore text outside the code block.
        Use the first code block, but prefer a fenced code block.
        If there are several fenced code blocks, concatenate only the fenced code blocks.

        Return a list of code blocks if any, otherwise return a list with a single string of code.
        """
        if match := list(FORMATTED_CODE_REGEX.finditer(code)):
            blocks = [block for block in match if block.group("block")]

            if len(blocks) > 1:
                codeblocks = [block.group("code") for block in blocks]
                info = "several code blocks"
            else:
                match = match[0] if len(blocks) == 0 else blocks[0]
                code, block, lang, delim = match.group("code", "block", "lang", "delim")
                codeblocks = [dedent(code)]
                if block:
                    info = (f"'{lang}' highlighted" if lang else "plain") + " code block"
                else:
                    info = f"{delim}-enclosed inline code"
        else:
            codeblocks = [dedent(RAW_CODE_REGEX.fullmatch(code).group("code"))]
            info = "unformatted or badly formatted code"

        code = "\n".join(codeblocks)
        log.trace(f"Extracted {info} for evaluation:\n{code}")
        return codeblocks


class Snekbox(Cog):
    """Safe evaluation of Python code using Snekbox."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.jobs = {}

    async def post_job(self, code: str, *, args: Optional[list[str]] = None) -> dict:
        """Send a POST request to the Snekbox API to evaluate code and return the results."""
        url = URLs.snekbox_eval_api
        data = {"input": code}

        if args is not None:
            data["args"] = args

        async with self.bot.http_session.post(url, json=data, raise_for_status=True) as resp:
            return await resp.json()

    async def upload_output(self, output: str) -> Optional[str]:
        """Upload the job's output to a paste service and return a URL to it if successful."""
        log.trace("Uploading full output to paste service...")

        if len(output) > MAX_PASTE_LEN:
            log.info("Full output is too long to upload")
            return "too long to upload"
        return await send_to_paste_service(output, extension="txt")

    @staticmethod
    def prepare_timeit_input(codeblocks: list[str]) -> tuple[str, list[str]]:
        """
        Join the codeblocks into a single string, then return the code and the arguments in a tuple.

        If there are multiple codeblocks, insert the first one into the wrapped setup code.
        """
        args = ["-m", "timeit"]
        setup = ""
        if len(codeblocks) > 1:
            setup = codeblocks.pop(0)

        code = "\n".join(codeblocks)

        args.extend(["-s", TIMEIT_SETUP_WRAPPER.format(setup=setup)])

        return code, args

    @staticmethod
    def get_results_message(results: dict, job_name: str) -> Tuple[str, str]:
        """Return a user-friendly message and error corresponding to the process's return code."""
        stdout, returncode = results["stdout"], results["returncode"]
        msg = f"Your {job_name} job has completed with return code {returncode}"
        error = ""

        if returncode is None:
            msg = f"Your {job_name} job has failed"
            error = stdout.strip()
        elif returncode == 128 + SIGKILL:
            msg = f"Your {job_name} job timed out or ran out of memory"
        elif returncode == 255:
            msg = f"Your {job_name} job has failed"
            error = "A fatal NsJail error occurred"
        else:
            # Try to append signal's name if one exists
            try:
                name = Signals(returncode - 128).name
                msg = f"{msg} ({name})"
            except ValueError:
                pass

        return msg, error

    @staticmethod
    def get_status_emoji(results: dict) -> str:
        """Return an emoji corresponding to the status code or lack of output in result."""
        if not results["stdout"].strip():  # No output
            return ":warning:"
        elif results["returncode"] == 0:  # No error
            return ":white_check_mark:"
        else:  # Exception
            return ":x:"

    async def format_output(self, output: str) -> Tuple[str, Optional[str]]:
        """
        Format the output and return a tuple of the formatted output and a URL to the full output.

        Prepend each line with a line number. Truncate if there are over 10 lines or 1000 characters
        and upload the full output to a paste service.
        """
        output = output.rstrip("\n")
        original_output = output  # To be uploaded to a pasting service if needed
        paste_link = None

        if "<@" in output:
            output = output.replace("<@", "<@\u200B")  # Zero-width space

        if "<!@" in output:
            output = output.replace("<!@", "<!@\u200B")  # Zero-width space

        if ESCAPE_REGEX.findall(output):
            paste_link = await self.upload_output(original_output)
            return "Code block escape attempt detected; will not output result", paste_link

        truncated = False
        lines = output.count("\n")

        if lines > 0:
            output = [f"{i:03d} | {line}" for i, line in enumerate(output.split('\n'), 1)]
            output = output[:11]  # Limiting to only 11 lines
            output = "\n".join(output)

        if lines > 10:
            truncated = True
            if len(output) >= 1000:
                output = f"{output[:1000]}\n... (truncated - too long, too many lines)"
            else:
                output = f"{output}\n... (truncated - too many lines)"
        elif len(output) >= 1000:
            truncated = True
            output = f"{output[:1000]}\n... (truncated - too long)"

        if truncated:
            paste_link = await self.upload_output(original_output)

        output = output or "[No output]"

        return output, paste_link

    async def send_job(
        self,
        ctx: Context,
        code: str,
        *,
        args: Optional[list[str]] = None,
        job_name: str
    ) -> Message:
        """
        Evaluate code, format it, and send the output to the corresponding channel.

        Return the bot response.
        """
        async with ctx.typing():
            results = await self.post_job(code, args=args)
            msg, error = self.get_results_message(results, job_name)

            if error:
                output, paste_link = error, None
            else:
                log.trace("Formatting output...")
                output, paste_link = await self.format_output(results["stdout"])

            icon = self.get_status_emoji(results)
            msg = f"{ctx.author.mention} {icon} {msg}.\n\n```\n{output}\n```"
            if paste_link:
                msg = f"{msg}\nFull output: {paste_link}"

            # Collect stats of job fails + successes
            if icon == ":x:":
                self.bot.stats.incr("snekbox.python.fail")
            else:
                self.bot.stats.incr("snekbox.python.success")

            filter_cog = self.bot.get_cog("Filtering")
            filter_triggered = False
            if filter_cog:
                filter_triggered = await filter_cog.filter_snekbox_output(msg, ctx.message)
            if filter_triggered:
                response = await ctx.send("Attempt to circumvent filter detected. Moderator team has been alerted.")
            else:
                allowed_mentions = AllowedMentions(everyone=False, roles=False, users=[ctx.author])
                response = await ctx.send(msg, allowed_mentions=allowed_mentions)
            scheduling.create_task(wait_for_deletion(response, (ctx.author.id,)), event_loop=self.bot.loop)

            log.info(f"{ctx.author}'s {job_name} job had a return code of {results['returncode']}")
        return response

    async def continue_job(
        self, ctx: Context, response: Message, command: Command
    ) -> tuple[Optional[str], Optional[list[str]]]:
        """
        Check if the job's session should continue.

        If the code is to be re-evaluated, return the new code, and the args if the command is the timeit command.
        Otherwise return (None, None) if the job's session should be terminated.
        """
        _predicate_message_edit = partial(predicate_message_edit, ctx)
        _predicate_emoji_reaction = partial(predicate_emoji_reaction, ctx)

        with contextlib.suppress(NotFound):
            try:
                _, new_message = await self.bot.wait_for(
                    'message_edit',
                    check=_predicate_message_edit,
                    timeout=REDO_TIMEOUT
                )
                await ctx.message.add_reaction(REDO_EMOJI)
                await self.bot.wait_for(
                    'reaction_add',
                    check=_predicate_emoji_reaction,
                    timeout=10
                )

                code = await self.get_code(new_message, ctx.command)
                await ctx.message.clear_reaction(REDO_EMOJI)
                with contextlib.suppress(HTTPException):
                    await response.delete()

                if code is None:
                    return None, None

            except asyncio.TimeoutError:
                await ctx.message.clear_reaction(REDO_EMOJI)
                return None, None

            codeblocks = await CodeblockConverter.convert(ctx, code)

            if command is self.timeit_command:
                return self.prepare_timeit_input(codeblocks)
            else:
                return "\n".join(codeblocks), None

        return None, None

    async def get_code(self, message: Message, command: Command) -> Optional[str]:
        """
        Return the code from `message` to be evaluated.

        If the message is an invocation of the command, return the first argument or None if it
        doesn't exist. Otherwise, return the full content of the message.
        """
        log.trace(f"Getting context for message {message.id}.")
        new_ctx = await self.bot.get_context(message)

        if new_ctx.command is command:
            log.trace(f"Message {message.id} invokes {command} command.")
            split = message.content.split(maxsplit=1)
            code = split[1] if len(split) > 1 else None
        else:
            log.trace(f"Message {message.id} does not invoke {command} command.")
            code = message.content

        return code

    async def run_job(
        self,
        job_name: str,
        ctx: Context,
        code: str,
        *,
        args: Optional[list[str]] = None,
    ) -> None:
        """Handles checks, stats and re-evaluation of a snekbox job."""
        if ctx.author.id in self.jobs:
            await ctx.send(
                f"{ctx.author.mention} You've already got a job running - "
                "please wait for it to finish!"
            )
            return

        if Roles.helpers in (role.id for role in ctx.author.roles):
            self.bot.stats.incr("snekbox_usages.roles.helpers")
        else:
            self.bot.stats.incr("snekbox_usages.roles.developers")

        if ctx.channel.category_id == Categories.help_in_use:
            self.bot.stats.incr("snekbox_usages.channels.help")
        elif ctx.channel.id == Channels.bot_commands:
            self.bot.stats.incr("snekbox_usages.channels.bot_commands")
        else:
            self.bot.stats.incr("snekbox_usages.channels.topical")

        log.info(f"Received code from {ctx.author} for evaluation:\n{code}")

        while True:
            self.jobs[ctx.author.id] = datetime.datetime.now()
            try:
                response = await self.send_job(ctx, code, args=args, job_name=job_name)
            finally:
                del self.jobs[ctx.author.id]

            code, args = await self.continue_job(ctx, response, ctx.command)
            if not code:
                break
            log.info(f"Re-evaluating code from message {ctx.message.id}:\n{code}")

    @command(name="eval", aliases=("e",))
    @guild_only()
    @redirect_output(
        destination_channel=Channels.bot_commands,
        bypass_roles=SNEKBOX_ROLES,
        categories=NO_SNEKBOX_CATEGORIES,
        channels=NO_SNEKBOX_CHANNELS,
        ping_user=False
    )
    async def eval_command(self, ctx: Context, *, code: CodeblockConverter) -> None:
        """
        Run Python code and get the results.

        This command supports multiple lines of code, including code wrapped inside a formatted code
        block. Code can be re-evaluated by editing the original message within 10 seconds and
        clicking the reaction that subsequently appears.

        We've done our best to make this sandboxed, but do let us know if you manage to find an
        issue with it!
        """
        await self.run_job("eval", ctx, "\n".join(code))

    @command(name="timeit", aliases=("ti",))
    @guild_only()
    @redirect_output(
        destination_channel=Channels.bot_commands,
        bypass_roles=SNEKBOX_ROLES,
        categories=NO_SNEKBOX_CATEGORIES,
        channels=NO_SNEKBOX_CHANNELS,
        ping_user=False
    )
    async def timeit_command(self, ctx: Context, *, code: CodeblockConverter) -> None:
        """
        Profile Python Code to find execution time.

        This command supports multiple lines of code, including code wrapped inside a formatted code
        block. Code can be re-evaluated by editing the original message within 10 seconds and
        clicking the reaction that subsequently appears.

        If multiple formatted codeblocks are provided, the first one will be the setup code, which will
        not be timed. The remaining codeblocks will be joined together and timed.

        We've done our best to make this sandboxed, but do let us know if you manage to find an
        issue with it!
        """
        code, args = self.prepare_timeit_input(code)

        await self.run_job("timeit", ctx, code=code, args=args)


def predicate_message_edit(ctx: Context, old_msg: Message, new_msg: Message) -> bool:
    """Return True if the edited message is the context message and the content was indeed modified."""
    return new_msg.id == ctx.message.id and old_msg.content != new_msg.content


def predicate_emoji_reaction(ctx: Context, reaction: Reaction, user: User) -> bool:
    """Return True if the reaction REDO_EMOJI was added by the context message author on this message."""
    return reaction.message.id == ctx.message.id and user.id == ctx.author.id and str(reaction) == REDO_EMOJI


def setup(bot: Bot) -> None:
    """Load the Snekbox cog."""
    bot.add_cog(Snekbox(bot))
