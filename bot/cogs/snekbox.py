import datetime
import logging
import random
import re
import textwrap
from typing import Optional, Tuple

from discord import Colour, Embed
from discord.ext.commands import (
    Bot, CommandError, Context, NoPrivateMessage, command, guild_only
)

from bot.constants import Channels, ERROR_REPLIES, NEGATIVE_REPLIES, Roles, URLs
from bot.decorators import InChannelCheckFailure, in_channel
from bot.utils.messages import wait_for_deletion


log = logging.getLogger(__name__)

CODE_TEMPLATE = """
venv_file = "/snekbox/.venv/bin/activate_this.py"
exec(open(venv_file).read(), dict(__file__=venv_file))

try:
{CODE}
except Exception as e:
    print(e)
"""

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

BYPASS_ROLES = (Roles.owner, Roles.admin, Roles.moderator, Roles.helpers)


class Snekbox:
    """
    Safe evaluation using Snekbox
    """

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
        url = URLs.paste_service.format(key="documents")
        try:
            async with self.bot.http_session.post(url, data=output, raise_for_status=True) as resp:
                data = await resp.json()

            if "key" in data:
                return URLs.paste_service.format(key=data["key"])
        except Exception:
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

        code = textwrap.indent(code, "    ")
        return CODE_TEMPLATE.replace("{CODE}", code)

    async def format_output(self, output: str) -> Tuple[str, Optional[str]]:
        """
        Format the output and return a tuple of the formatted output and a URL to the full output.

        Prepend each line with a line number. Truncate if there are over 10 lines or 1000 characters
        and upload the full output to a paste service.
        """
        output = output.strip(" \n")
        paste_link = None

        if "<@" in output:
            output = output.replace("<@", "<@\u200B")  # Zero-width space

        if "<!@" in output:
            output = output.replace("<!@", "<!@\u200B")  # Zero-width space

        if ESCAPE_REGEX.findall(output):
            return "Code block escape attempt detected; will not output result", paste_link

        # the original output, to send to a pasting service if needed
        full_output = output
        truncated = False
        if output.count("\n") > 0:
            output = [f"{i:03d} | {line}" for i, line in enumerate(output.split("\n"), start=1)]
            output = "\n".join(output)

        if output.count("\n") > 10:
            output = "\n".join(output.split("\n")[:10])

            if len(output) >= 1000:
                output = f"{output[:1000]}\n... (truncated - too long, too many lines)"
            else:
                output = f"{output}\n... (truncated - too many lines)"
            truncated = True

        elif len(output) >= 1000:
            output = f"{output[:1000]}\n... (truncated - too long)"
            truncated = True

        if truncated:
            paste_link = await self.upload_output(full_output)

        return output.strip(), paste_link

    @command(name='eval', aliases=('e',))
    @guild_only()
    @in_channel(Channels.bot, bypass_roles=BYPASS_ROLES)
    async def eval_command(self, ctx: Context, *, code: str = None):
        """
        Run some code. get the result back. We've done our best to make this safe, but do let us know if you
        manage to find an issue with it!

        This command supports multiple lines of code, including code wrapped inside a formatted code block.
        """

        if ctx.author.id in self.jobs:
            await ctx.send(f"{ctx.author.mention} You've already got a job running - please wait for it to finish!")
            return

        if not code:  # None or empty string
            return await ctx.invoke(self.bot.get_command("help"), "eval")

        log.info(f"Received code from {ctx.author.name}#{ctx.author.discriminator} for evaluation:\n{code}")
        self.jobs[ctx.author.id] = datetime.datetime.now()

        code = self.prepare_input(code)

        try:
            async with ctx.typing():
                message = ...  # TODO
                output, paste_link = await self.format_output(message)

                if output:
                    if paste_link:
                        msg = f"{ctx.author.mention} Your eval job has completed.\n\n```py\n{output}\n```" \
                              f"\nFull output: {paste_link}"
                    else:
                        msg = f"{ctx.author.mention} Your eval job has completed.\n\n```py\n{output}\n```"

                    response = await ctx.send(msg)
                    self.bot.loop.create_task(wait_for_deletion(response, user_ids=(ctx.author.id,), client=ctx.bot))

                else:
                    await ctx.send(
                        f"{ctx.author.mention} Your eval job has completed.\n\n```py\n[No output]\n```"
                    )

            del self.jobs[ctx.author.id]
        except Exception:
            del self.jobs[ctx.author.id]
            raise

    @eval_command.error
    async def eval_command_error(self, ctx: Context, error: CommandError):
        embed = Embed(colour=Colour.red())

        if isinstance(error, NoPrivateMessage):
            embed.title = random.choice(NEGATIVE_REPLIES)
            embed.description = "You're not allowed to use this command in private messages."
            await ctx.send(embed=embed)

        elif isinstance(error, InChannelCheckFailure):
            embed.title = random.choice(NEGATIVE_REPLIES)
            embed.description = str(error)
            await ctx.send(embed=embed)

        else:
            original_error = getattr(error, 'original', "no original error")
            log.error(f"Unhandled error in snekbox eval: {error} ({original_error})")
            embed.title = random.choice(ERROR_REPLIES)
            embed.description = "Some unhandled error occurred. Sorry for that!"
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Snekbox(bot))
    log.info("Cog loaded: Snekbox")
