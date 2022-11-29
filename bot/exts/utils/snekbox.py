from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass, field
from functools import partial
from operator import attrgetter
from signal import Signals
from textwrap import dedent
from typing import Literal, Optional, TYPE_CHECKING, Tuple

from botcore.utils import interactions
from botcore.utils.regex import FORMATTED_CODE_REGEX, RAW_CODE_REGEX
from discord import AllowedMentions, HTTPException, Interaction, Message, NotFound, Reaction, User, enums, ui
from discord.ext.commands import Cog, Command, Context, Converter, command, guild_only

from bot.bot import Bot
from bot.constants import Categories, Channels, MODERATION_ROLES, Roles, URLs
from bot.decorators import redirect_output
from bot.exts.utils.snekio import FileAttachment, sizeof_fmt, FILE_SIZE_LIMIT
from bot.log import get_logger
from bot.utils import send_to_paste_service
from bot.utils.lock import LockedResourceError, lock_arg
from bot.utils.services import PasteTooLongError, PasteUploadError

if TYPE_CHECKING:
    from bot.exts.filters.filtering import Filtering

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

MAX_PASTE_LENGTH = 10_000

# The Snekbox commands' whitelists and blacklists.
NO_SNEKBOX_CHANNELS = (Channels.python_general,)
NO_SNEKBOX_CATEGORIES = ()
SNEKBOX_ROLES = (Roles.helpers, Roles.moderators, Roles.admins, Roles.owners, Roles.python_community, Roles.partners)

SIGKILL = 9

REDO_EMOJI = '\U0001f501'  # :repeat:
REDO_TIMEOUT = 30

PythonVersion = Literal["3.10", "3.11"]


@dataclass
class EvalJob:
    """Job to be evaluated by snekbox."""

    args: list[str]
    files: list[FileAttachment] = field(default_factory=list)
    name: str = "eval"
    version: PythonVersion = "3.11"

    @classmethod
    def from_code(cls, code: str, path: str = "main.py") -> EvalJob:
        """Create an EvalJob from a code string."""
        return cls(
            args=[path],
            files=[FileAttachment(path, code.encode())],
        )

    def as_version(self, version: PythonVersion) -> EvalJob:
        """Return a copy of the job with a different Python version."""
        return EvalJob(
            args=self.args,
            files=self.files,
            name=self.name,
            version=version,
        )

    def to_dict(self) -> dict[str, list[str | dict[str, str]]]:
        """Convert the job to a dict."""
        return {
            "args": self.args,
            "files": [file.to_dict() for file in self.files],
        }


@dataclass(frozen=True)
class EvalResult:
    """The result of an eval job."""

    stdout: str
    returncode: int | None
    files: list[FileAttachment] = field(default_factory=list)
    err_files: list[str] = field(default_factory=list)

    @property
    def status_emoji(self):
        """Return an emoji corresponding to the status code or lack of output in result."""
        # If there are attachments, skip empty output warning
        if not self.stdout.strip() and not self.files:  # No output
            return ":warning:"
        elif self.returncode == 0:  # No error
            return ":white_check_mark:"
        else:  # Exception
            return ":x:"

    def message(self, job: EvalJob) -> tuple[str, str]:
        """Return a user-friendly message and error corresponding to the process's return code."""
        msg = f"Your {job.version} {job.name} job has completed with return code {self.returncode}"
        error = ""

        if self.returncode is None:
            msg = f"Your {job.version} {job.name} job has failed"
            error = self.stdout.strip()
        elif self.returncode == 128 + SIGKILL:
            msg = f"Your {job.version} {job.name} job timed out or ran out of memory"
        elif self.returncode == 255:
            msg = f"Your {job.version} {job.name} job has failed"
            error = "A fatal NsJail error occurred"
        else:
            # Try to append signal's name if one exists
            with contextlib.suppress(ValueError):
                name = Signals(self.returncode - 128).name
                msg = f"{msg} ({name})"

        # Add error message for failed attachments
        if self.err_files:
            failed_files = f"({', '.join(self.err_files)})"
            msg += (
                f".\n\n> Some attached files were not able to be uploaded {failed_files}."
                f" Check that the file size is less than {sizeof_fmt(FILE_SIZE_LIMIT)}"
            )

        return msg, error

    @classmethod
    def from_dict(cls, data: dict[str, str | int | list[dict[str, str]]]) -> EvalResult:
        """Create an EvalResult from a dict."""
        res = cls(
            stdout=data["stdout"],
            returncode=data["returncode"],
        )

        for file in data.get("files", []):
            try:
                res.files.append(FileAttachment.from_dict(file))
            except ValueError as e:
                log.info(f"Failed to parse file from snekbox response: {e}")
                res.err_files.append(file["path"])

        return res


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


class PythonVersionSwitcherButton(ui.Button):
    """A button that allows users to re-run their eval command in a different Python version."""

    def __init__(
            self,
            version_to_switch_to: PythonVersion,
            snekbox_cog: Snekbox,
            ctx: Context,
            job: EvalJob,
    ) -> None:
        self.version_to_switch_to = version_to_switch_to
        super().__init__(label=f"Run in {self.version_to_switch_to}", style=enums.ButtonStyle.primary)

        self.snekbox_cog = snekbox_cog
        self.ctx = ctx
        self.job = job

    async def callback(self, interaction: Interaction) -> None:
        """
        Tell snekbox to re-run the user's code in the alternative Python version.

        Use a task calling snekbox, as run_job is blocking while it waits for edit/reaction on the message.
        """
        # Defer response here so that the Discord UI doesn't mark this interaction as failed if the job
        # takes too long to run.
        await interaction.response.defer()

        with contextlib.suppress(NotFound):
            # Suppress delete to cover the case where a user re-runs code and very quickly clicks the button.
            # The log arg on send_job will stop the actual job from running.
            await interaction.message.delete()

        await self.snekbox_cog.run_job(self.ctx, self.job.as_version(self.version_to_switch_to))


class Snekbox(Cog):
    """Safe evaluation of Python code using Snekbox."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.jobs = {}

    def build_python_version_switcher_view(
            self,
            current_python_version: PythonVersion,
            ctx: Context,
            job: EvalJob,
    ) -> interactions.ViewWithUserAndRoleCheck:
        """Return a view that allows the user to change what version of Python their code is run on."""
        if current_python_version == "3.10":
            alt_python_version = "3.11"
        else:
            alt_python_version = "3.10"

        view = interactions.ViewWithUserAndRoleCheck(
            allowed_users=(ctx.author.id,),
            allowed_roles=MODERATION_ROLES,
        )
        view.add_item(PythonVersionSwitcherButton(alt_python_version, self, ctx, job))
        view.add_item(interactions.DeleteMessageButton())

        return view

    async def post_job(self, job: EvalJob) -> EvalResult:
        """Send a POST request to the Snekbox API to evaluate code and return the results."""
        if job.version == "3.10":
            url = URLs.snekbox_eval_api
        else:
            url = URLs.snekbox_311_eval_api

        data = job.to_dict()

        async with self.bot.http_session.post(url, json=data, raise_for_status=True) as resp:
            return await resp.json()

    @staticmethod
    async def upload_output(output: str) -> Optional[str]:
        """Upload the job's output to a paste service and return a URL to it if successful."""
        log.trace("Uploading full output to paste service...")

        try:
            return await send_to_paste_service(output, extension="txt", max_length=MAX_PASTE_LENGTH)
        except PasteTooLongError:
            return "too long to upload"
        except PasteUploadError:
            return "unable to upload"

    @staticmethod
    def prepare_timeit_input(codeblocks: list[str]) -> list[str]:
        """
        Join the codeblocks into a single string, then return the code and the arguments in a tuple.

        If there are multiple codeblocks, insert the first one into the wrapped setup code.
        """
        args = ["-m", "timeit"]
        setup_code = codeblocks.pop(0) if len(codeblocks) > 1 else ""
        code = "\n".join(codeblocks)

        args.extend(["-s", TIMEIT_SETUP_WRAPPER.format(setup=setup_code), code])
        return args

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

    @lock_arg("snekbox.send_job", "ctx", attrgetter("author.id"), raise_error=True)
    async def send_job(self, ctx: Context, job: EvalJob) -> Message:
        """
        Evaluate code, format it, and send the output to the corresponding channel.

        Return the bot response.
        """
        async with ctx.typing():
            result = await self.post_job(job)
            msg, error = result.message(job)

            if error:
                output, paste_link = error, None
            else:
                log.trace("Formatting output...")
                output, paste_link = await self.format_output(result.stdout)

            if result.files and output in ("[No output]", ""):
                msg = f"{ctx.author.mention} {result.status_emoji} {msg}.\n"
            else:
                msg = f"{ctx.author.mention} {result.status_emoji} {msg}.\n\n```\n{output}\n```"

            if paste_link:
                msg = f"{msg}\nFull output: {paste_link}"

            # Collect stats of job fails + successes
            if result.returncode != 0:
                self.bot.stats.incr("snekbox.python.fail")
            else:
                self.bot.stats.incr("snekbox.python.success")

            filter_cog: Filtering | None = self.bot.get_cog("Filtering")
            filter_triggered = False
            if filter_cog:
                filter_triggered = await filter_cog.filter_snekbox_output(msg, ctx.message)
            if filter_triggered:
                response = await ctx.send("Attempt to circumvent filter detected. Moderator team has been alerted.")
            else:
                allowed_mentions = AllowedMentions(everyone=False, roles=False, users=[ctx.author])
                view = self.build_python_version_switcher_view(job.version, ctx, job)

                # Attach files if provided
                files = [f.to_file() for f in result.files]
                response = await ctx.send(msg, allowed_mentions=allowed_mentions, view=view, files=files)
                view.message = response

            log.info(f"{ctx.author}'s {job.name} job had a return code of {result.returncode}")
        return response

    async def continue_job(
        self, ctx: Context, response: Message, job_name: str
    ) -> EvalJob | None:
        """
        Check if the job's session should continue.

        If the code is to be re-evaluated, return the new EvalJob.
        Otherwise, return None if the job's session should be terminated.
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

                # Ensure the response that's about to be edited is still the most recent.
                # This could have already been updated via a button press to switch to an alt Python version.
                if self.jobs[ctx.message.id] != response.id:
                    return None

                code = await self.get_code(new_message, ctx.command)
                await ctx.message.clear_reaction(REDO_EMOJI)
                with contextlib.suppress(HTTPException):
                    await response.delete()

                if code is None:
                    return None

            except asyncio.TimeoutError:
                await ctx.message.clear_reaction(REDO_EMOJI)
                return None

            codeblocks = await CodeblockConverter.convert(ctx, code)

            if job_name == "timeit":
                return EvalJob(self.prepare_timeit_input(codeblocks))
            else:
                return EvalJob.from_code("\n".join(codeblocks))

        return None

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
        ctx: Context,
        job: EvalJob,
    ) -> None:
        """Handles checks, stats and re-evaluation of a snekbox job."""
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

        log.info(f"Received code from {ctx.author} for evaluation:\n{job}")

        while True:
            try:
                response = await self.send_job(ctx, job)
            except LockedResourceError:
                await ctx.send(
                    f"{ctx.author.mention} You've already got a job running - "
                    "please wait for it to finish!"
                )
                return

            # Store the bots response message id per invocation, to ensure the `wait_for`s in `continue_job`
            # don't trigger if the response has already been replaced by a new response.
            # This can happen when a button is pressed and then original code is edited and re-run.
            self.jobs[ctx.message.id] = response.id

            job = await self.continue_job(ctx, response, job.name)
            if not job:
                break
            log.info(f"Re-evaluating code from message {ctx.message.id}:\n{job}")

    @command(name="eval", aliases=("e",), usage="[python_version] <code, ...>")
    @guild_only()
    @redirect_output(
        destination_channel=Channels.bot_commands,
        bypass_roles=SNEKBOX_ROLES,
        categories=NO_SNEKBOX_CATEGORIES,
        channels=NO_SNEKBOX_CHANNELS,
        ping_user=False
    )
    async def eval_command(
        self,
        ctx: Context,
        python_version: PythonVersion | None,
        *,
        code: CodeblockConverter
    ) -> None:
        """
        Run Python code and get the results.

        This command supports multiple lines of code, including code wrapped inside a formatted code
        block. Code can be re-evaluated by editing the original message within 10 seconds and
        clicking the reaction that subsequently appears.

        If multiple codeblocks are in a message, all of them will be joined and evaluated,
        ignoring the text outside them.

        By default, your code is run on Python's 3.11 beta release, to assist with testing. If you
        run into issues related to this Python version, you can request the bot to use Python
        3.10 by specifying the `python_version` arg and setting it to `3.10`.

        We've done our best to make this sandboxed, but do let us know if you manage to find an
        issue with it!
        """
        code: list[str]
        python_version = python_version or "3.11"
        job = EvalJob.from_code("\n".join(code)).as_version(python_version)
        await self.run_job(ctx, job)

    @command(name="timeit", aliases=("ti",), usage="[python_version] [setup_code] <code, ...>")
    @guild_only()
    @redirect_output(
        destination_channel=Channels.bot_commands,
        bypass_roles=SNEKBOX_ROLES,
        categories=NO_SNEKBOX_CATEGORIES,
        channels=NO_SNEKBOX_CHANNELS,
        ping_user=False
    )
    async def timeit_command(
        self,
        ctx: Context,
        python_version: PythonVersion | None,
        *,
        code: CodeblockConverter
    ) -> None:
        """
        Profile Python Code to find execution time.

        This command supports multiple lines of code, including code wrapped inside a formatted code
        block. Code can be re-evaluated by editing the original message within 10 seconds and
        clicking the reaction that subsequently appears.

        If multiple formatted codeblocks are provided, the first one will be the setup code, which will
        not be timed. The remaining codeblocks will be joined together and timed.

        By default your code is run on Python's 3.11 beta release, to assist with testing. If you
        run into issues related to this Python version, you can request the bot to use Python
        3.10 by specifying the `python_version` arg and setting it to `3.10`.

        We've done our best to make this sandboxed, but do let us know if you manage to find an
        issue with it!
        """
        code: list[str]
        python_version = python_version or "3.11"
        args = self.prepare_timeit_input(code)
        job = EvalJob(args, version=python_version, name="timeit")

        await self.run_job(ctx, job)


def predicate_message_edit(ctx: Context, old_msg: Message, new_msg: Message) -> bool:
    """Return True if the edited message is the context message and the content was indeed modified."""
    return new_msg.id == ctx.message.id and old_msg.content != new_msg.content


def predicate_emoji_reaction(ctx: Context, reaction: Reaction, user: User) -> bool:
    """Return True if the reaction REDO_EMOJI was added by the context message author on this message."""
    return reaction.message.id == ctx.message.id and user.id == ctx.author.id and str(reaction) == REDO_EMOJI


async def setup(bot: Bot) -> None:
    """Load the Snekbox cog."""
    await bot.add_cog(Snekbox(bot))
