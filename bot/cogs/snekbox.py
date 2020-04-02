import asyncio
import contextlib
import datetime
import logging
import re
import textwrap
from functools import partial
from signal import Signals
from typing import Optional, Tuple

from discord import HTTPException, Message, NotFound, Reaction, User
from discord.ext.commands import Cog, Context, command, guild_only

from bot.bot import Bot
from bot.constants import Channels, Roles, URLs
from bot.decorators import in_channel
from bot.utils.messages import wait_for_deletion

log = logging.getLogger(__name__)

ESCAPE_REGEX = re.compile("[`\u202E\u200B]{3,}")
FORMATTED_CODE_REGEX = re.compile(
    r"^\s*"                                 # any leading whitespace from the beginning of the string
    r"(?P<delim>(?P<block>```)|``?)"        # code delimiter: 1-3 backticks; (?P=block) only matches if it's a block
    r"(?(block)(?:(?P<lang>[a-z]+)\n)?)"    # if we're in a block, match optional language (only letters plus newline)
    r"(?:[ \t]*\n)*"                        # any blank (empty or tabs/spaces only) lines before the code
    r"(?P<code>.*?)"                        # extract all code inside the markup
    r"\s*"                                  # any more whitespace before the end of the code markup
    r"(?P=delim)"                           # match the exact same delimiter from the start again
    r"\s*$",                                # any trailing whitespace until the end of the string
    re.DOTALL | re.IGNORECASE               # "." also matches newlines, case insensitive
)
RAW_CODE_REGEX = re.compile(
    r"^(?:[ \t]*\n)*"                       # any blank (empty or tabs/spaces only) lines before the code
    r"(?P<code>.*?)"                        # extract all the rest as code
    r"\s*$",                                # any trailing whitespace until the end of the string
    re.DOTALL                               # "." also matches newlines
)

MAX_PASTE_LEN = 1000
EVAL_ROLES = (Roles.helpers, Roles.moderators, Roles.admins, Roles.owners, Roles.python_community, Roles.partners)

SIGKILL = 9

REEVAL_EMOJI = '\U0001f501'  # :repeat:


class Snekbox(Cog):
    """Safe evaluation of Python code using Snekbox."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.jobs = {}

    async def post_eval(self, code: str) -> dict:
        """Send a POST request to the Snekbox API to evaluate code and return the results."""
        url = URLs.snekbox_eval_api
        data = {"input": code}
        async with self.bot.http_session.post(url, json=data, raise_for_status=True) as resp:
            return await resp.json()

    async def upload_output(self, output: str) -> Optional[str]:
        """Upload the eval output to a paste service and return a URL to it if successful."""
        log.trace("Uploading full output to paste service...")

        if len(output) > MAX_PASTE_LEN:
            log.info("Full output is too long to upload")
            return "too long to upload"

        url = URLs.paste_service.format(key="documents")
        try:
            async with self.bot.http_session.post(url, data=output, raise_for_status=True) as resp:
                data = await resp.json()

            if "key" in data:
                return URLs.paste_service.format(key=data["key"])
        except Exception:
            # 400 (Bad Request) means there are too many characters
            log.exception("Failed to upload full output to paste service!")

    @staticmethod
    def prepare_input(code: str) -> str:
        """Extract code from the Markdown, format it, and insert it into the code template."""
        match = FORMATTED_CODE_REGEX.fullmatch(code)
        if match:
            code, block, lang, delim = match.group("code", "block", "lang", "delim")
            code = textwrap.dedent(code)
            if block:
                info = (f"'{lang}' highlighted" if lang else "plain") + " code block"
            else:
                info = f"{delim}-enclosed inline code"
            log.trace(f"Extracted {info} for evaluation:\n{code}")
        else:
            code = textwrap.dedent(RAW_CODE_REGEX.fullmatch(code).group("code"))
            log.trace(
                f"Eval message contains unformatted or badly formatted code, "
                f"stripping whitespace only:\n{code}"
            )

        return code

    @staticmethod
    def get_results_message(results: dict) -> Tuple[str, str]:
        """Return a user-friendly message and error corresponding to the process's return code."""
        stdout, returncode = results["stdout"], results["returncode"]
        msg = f"Your eval job has completed with return code {returncode}"
        error = ""

        if returncode is None:
            msg = "Your eval job has failed"
            error = stdout.strip()
        elif returncode == 128 + SIGKILL:
            msg = "Your eval job timed out or ran out of memory"
        elif returncode == 255:
            msg = "Your eval job has failed"
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
        log.trace("Formatting output...")

        output = output.rstrip("\n")
        original_output = output  # To be uploaded to a pasting service if needed
        paste_link = None

        if "<@" in output:
            output = output.replace("<@", "<@\u200B")  # Zero-width space

        if "<!@" in output:
            output = output.replace("<!@", "<!@\u200B")  # Zero-width space

        if ESCAPE_REGEX.findall(output):
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

    async def send_eval(self, ctx: Context, code: str) -> Message:
        """
        Evaluate code, format it, and send the output to the corresponding channel.

        Return the bot response.
        """
        async with ctx.typing():
            results = await self.post_eval(code)
            msg, error = self.get_results_message(results)

            if error:
                output, paste_link = error, None
            else:
                output, paste_link = await self.format_output(results["stdout"])

            icon = self.get_status_emoji(results)
            msg = f"{ctx.author.mention} {icon} {msg}.\n\n```py\n{output}\n```"
            if paste_link:
                msg = f"{msg}\nFull output: {paste_link}"

            response = await ctx.send(msg)
            self.bot.loop.create_task(
                wait_for_deletion(response, user_ids=(ctx.author.id,), client=ctx.bot)
            )

            log.info(f"{ctx.author}'s job had a return code of {results['returncode']}")
        return response

    async def continue_eval(self, ctx: Context, response: Message) -> Optional[str]:
        """
        Check if the eval session should continue.

        Return the new code to evaluate or None if the eval session should be terminated.
        """
        _predicate_eval_message_edit = partial(predicate_eval_message_edit, ctx)
        _predicate_emoji_reaction = partial(predicate_eval_emoji_reaction, ctx)

        with contextlib.suppress(NotFound):
            try:
                _, new_message = await self.bot.wait_for(
                    'message_edit',
                    check=_predicate_eval_message_edit,
                    timeout=10
                )
                await ctx.message.add_reaction(REEVAL_EMOJI)
                await self.bot.wait_for(
                    'reaction_add',
                    check=_predicate_emoji_reaction,
                    timeout=10
                )

                code = await self.get_code(new_message)
                await ctx.message.clear_reactions()
                with contextlib.suppress(HTTPException):
                    await response.delete()

            except asyncio.TimeoutError:
                await ctx.message.clear_reactions()
                return None

            return code

    async def get_code(self, message: Message) -> Optional[str]:
        """
        Return the code from `message` to be evaluated.

        If the message is an invocation of the eval command, return the first argument or None if it
        doesn't exist. Otherwise, return the full content of the message.
        """
        log.trace(f"Getting context for message {message.id}.")
        new_ctx = await self.bot.get_context(message)

        if new_ctx.command is self.eval_command:
            log.trace(f"Message {message.id} invokes eval command.")
            split = message.content.split(maxsplit=1)
            code = split[1] if len(split) > 1 else None
        else:
            log.trace(f"Message {message.id} does not invoke eval command.")
            code = message.content

        return code

    @command(name="eval", aliases=("e",))
    @guild_only()
    @in_channel(Channels.bot_commands, hidden_channels=(Channels.esoteric,), bypass_roles=EVAL_ROLES)
    async def eval_command(self, ctx: Context, *, code: str = None) -> None:
        """
        Run Python code and get the results.

        This command supports multiple lines of code, including code wrapped inside a formatted code
        block. Code can be re-evaluated by editing the original message within 10 seconds and
        clicking the reaction that subsequently appears.

        We've done our best to make this sandboxed, but do let us know if you manage to find an
        issue with it!
        """
        if ctx.author.id in self.jobs:
            await ctx.send(
                f"{ctx.author.mention} You've already got a job running - "
                "please wait for it to finish!"
            )
            return

        if not code:  # None or empty string
            await ctx.invoke(self.bot.get_command("help"), "eval")
            return

        log.info(f"Received code from {ctx.author} for evaluation:\n{code}")

        while True:
            self.jobs[ctx.author.id] = datetime.datetime.now()
            code = self.prepare_input(code)
            try:
                response = await self.send_eval(ctx, code)
            finally:
                del self.jobs[ctx.author.id]

            code = await self.continue_eval(ctx, response)
            if not code:
                break
            log.info(f"Re-evaluating code from message {ctx.message.id}:\n{code}")


def predicate_eval_message_edit(ctx: Context, old_msg: Message, new_msg: Message) -> bool:
    """Return True if the edited message is the context message and the content was indeed modified."""
    return new_msg.id == ctx.message.id and old_msg.content != new_msg.content


def predicate_eval_emoji_reaction(ctx: Context, reaction: Reaction, user: User) -> bool:
    """Return True if the reaction REEVAL_EMOJI was added by the context message author on this message."""
    return reaction.message.id == ctx.message.id and user.id == ctx.author.id and str(reaction) == REEVAL_EMOJI


def setup(bot: Bot) -> None:
    """Load the Snekbox cog."""
    bot.add_cog(Snekbox(bot))
