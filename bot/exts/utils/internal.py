import contextlib
import inspect
import pprint
import re
import textwrap
import traceback
from collections import Counter
from io import StringIO
from typing import Any

import arrow
import discord
from discord.ext.commands import Cog, Context, group, has_any_role, is_owner
from pydis_core.utils.paste_service import PasteFile, PasteTooLongError, PasteUploadError, send_to_paste_service

from bot.bot import Bot
from bot.constants import BaseURLs, DEBUG_MODE, Roles
from bot.log import get_logger
from bot.utils import find_nth_occurrence

log = get_logger(__name__)


class Internal(Cog):
    """Administrator and Core Developer commands."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.env = {}
        self.ln = 0
        self.stdout = StringIO()

        self.socket_since = arrow.utcnow()
        self.socket_event_total = 0
        self.socket_events = Counter()

        if DEBUG_MODE:
            self.eval.add_check(is_owner().predicate)

    @Cog.listener()
    async def on_socket_event_type(self, event_type: str) -> None:
        """When a websocket event is received, increase our counters."""
        self.socket_event_total += 1
        self.socket_events[event_type] += 1

    def _format(self, inp: str, out: Any) -> tuple[str, discord.Embed | None]:
        """Format the eval output into a string & attempt to format it into an Embed."""
        self._ = out

        res = ""

        # Erase temp input we made
        if inp.startswith("_ = "):
            inp = inp[4:]

        # Get all non-empty lines
        lines = [line for line in inp.split("\n") if line.strip()]
        if len(lines) != 1:
            lines += [""]

        # Create the input dialog
        for i, line in enumerate(lines):
            if i == 0:
                # Start dialog
                start = f"In [{self.ln}]: "

            else:
                # Indent the 3 dots correctly;
                # Normally, it's something like
                # In [X]:
                #    ...:
                #
                # But if it's
                # In [XX]:
                #    ...:
                #
                # You can see it doesn't look right.
                # This code simply indents the dots
                # far enough to align them.
                # we first `str()` the line number
                # then we get the length
                # and use `str.rjust()`
                # to indent it.
                start = "...: ".rjust(len(str(self.ln)) + 7)

            if i == len(lines) - 2:
                if line.startswith("return"):
                    line = line[6:].strip()

            # Combine everything
            res += (start + line + "\n")

        self.stdout.seek(0)
        text = self.stdout.read()
        self.stdout.close()
        self.stdout = StringIO()

        if text:
            res += (text + "\n")

        if out is None:
            # No output, return the input statement
            return (res, None)

        res += f"Out[{self.ln}]: "

        if isinstance(out, discord.Embed):
            # We made an embed? Send that as embed
            res += "<Embed>"
            res = (res, out)

        else:
            if (isinstance(out, str) and out.startswith("Traceback (most recent call last):\n")):
                # Leave out the traceback message
                out = "\n" + "\n".join(out.split("\n")[1:])

            if isinstance(out, str):
                pretty = out
            else:
                pretty = pprint.pformat(out, compact=True, width=60)

            if pretty != str(out):
                # We're using the pretty version, start on the next line
                res += "\n"

            if pretty.count("\n") > 20:
                # Text too long, shorten
                li = pretty.split("\n")

                pretty = ("\n".join(li[:3])  # First 3 lines
                          + "\n ...\n"  # Ellipsis to indicate removed lines
                          + "\n".join(li[-3:]))  # last 3 lines

            # Add the output
            res += pretty
            res = (res, None)

        return res  # Return (text, embed)

    async def _eval(self, ctx: Context, code: str) -> discord.Message | None:
        """Eval the input code string & send an embed to the invoking context."""
        self.ln += 1

        if code.startswith("exit"):
            self.ln = 0
            self.env = {}
            return await ctx.send("```Reset history!```")

        env = {
            "message": ctx.message,
            "author": ctx.message.author,
            "channel": ctx.channel,
            "guild": ctx.guild,
            "ctx": ctx,
            "self": self,
            "bot": self.bot,
            "inspect": inspect,
            "discord": discord,
            "contextlib": contextlib
        }

        self.env.update(env)

        # Ignore this code, it works
        code_ = """
async def func():  # (None,) -> Any
    try:
        with contextlib.redirect_stdout(self.stdout):
{}
        if '_' in locals():
            if inspect.isawaitable(_):
                _ = await _
            return _
    finally:
        self.env.update(locals())
""".format(textwrap.indent(code, "            "))

        try:
            exec(code_, self.env)  # noqa: S102
            func = self.env["func"]
            res = await func()

        except Exception:
            res = traceback.format_exc()

        out, embed = self._format(code, res)
        out = out.rstrip("\n")  # Strip empty lines from output

        # Truncate output to max 15 lines or 1500 characters
        newline_truncate_index = find_nth_occurrence(out, "\n", 15)

        if newline_truncate_index is None or newline_truncate_index > 1500:
            truncate_index = 1500
        else:
            truncate_index = newline_truncate_index

        if len(out) > truncate_index:
            file = PasteFile(content=out)
            try:
                resp = await send_to_paste_service(
                    files=[file],
                    http_session=self.bot.http_session,
                    paste_url=BaseURLs.paste_url,
                )
            except PasteTooLongError:
                paste_text = "too long to upload to paste service."
            except PasteUploadError:
                paste_text = "failed to upload contents to paste service."
            else:
                paste_text = f"full contents at {resp.link}"

            await ctx.send(
                f"```py\n{out[:truncate_index]}\n```"
                f"... response truncated; {paste_text}",
                embed=embed
            )
            return None

        await ctx.send(f"```py\n{out}```", embed=embed)
        return None

    @group(name="internal", aliases=("int",))
    @has_any_role(Roles.owners, Roles.admins, Roles.core_developers)
    async def internal_group(self, ctx: Context) -> None:
        """Internal commands. Top secret!"""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @internal_group.command(name="eval", aliases=("e",))
    @has_any_role(Roles.admins, Roles.owners)
    async def eval(self, ctx: Context, *, code: str) -> None:
        """Run eval in a REPL-like format."""
        code = code.strip("`")
        if re.match("py(thon)?\n", code):
            code = "\n".join(code.split("\n")[1:])

        if not re.search(  # Check if it's an expression
                r"^(return|import|for|while|def|class|"
                r"from|exit|[a-zA-Z0-9]+\s*=)", code, re.M) and len(
                    code.split("\n")) == 1:
            code = "_ = " + code

        await self._eval(ctx, code)

    @internal_group.command(name="socketstats", aliases=("socket", "stats"))
    @has_any_role(Roles.admins, Roles.owners, Roles.core_developers)
    async def socketstats(self, ctx: Context) -> None:
        """Fetch information on the socket events received from Discord."""
        running_s = (arrow.utcnow() - self.socket_since).total_seconds()

        per_s = self.socket_event_total / running_s

        stats_embed = discord.Embed(
            title="WebSocket statistics",
            description=f"Receiving {per_s:0.2f} events per second.",
            color=discord.Color.og_blurple()
        )

        for event_type, count in self.socket_events.most_common(25):
            stats_embed.add_field(name=event_type, value=f"{count:,}", inline=True)

        await ctx.send(embed=stats_embed)


async def setup(bot: Bot) -> None:
    """Load the Internal cog."""
    await bot.add_cog(Internal(bot))
