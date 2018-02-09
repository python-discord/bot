# coding=utf-8

import contextlib
from io import StringIO
import inspect
import textwrap
import pprint
import traceback
import re

import discord
from discord.ext.commands import AutoShardedBot, command

from bot.constants import OWNER_ROLE
from bot.decorators import with_role
from bot.interpreter import Interpreter


class EvalCog:  # Named this way because a flake8 plugin isn't case-sensitive
    """
    Bot owner only: Evaluate Python code

    Made by martmists
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.env = {}
        self.ln = 0
        self.stdout = StringIO()

        self.interpreter = Interpreter(bot)

    def _format(self, inp, out):
        self._ = out

        res = ""

        # Erase temp input we made
        if inp.startswith("_ = "):
            inp = inp[4:]

        lines = [l for l in inp.split("\n") if l.strip()]
        if len(lines) != 1:
            lines += [""]

        # Create the inpit dialog
        for i, line in enumerate(lines):
            if i == 0:
                s = f"In [{self.ln}]: "

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
                # and do a simple {:<LENGHT}
                # to indent it.
                s = f"{'':<{len(str(self.ln))+2}}...: "

            if i == len(lines) - 2:
                if line.startswith("return"):
                    line = line[6:].strip()

            res += s + line + "\n"

        self.stdout.seek(0)
        text = self.stdout.read()
        self.stdout.close()
        self.stdout = io.StringIO()

        if text:
            res += text + "\n"

        if out is None:
            # No output, return the input statement
            return (res, None)

        res += f"Out[{self.ln}]: "

        if isinstance(out, discord.Embed):
            # We made an embed? Send that as embed
            res += "<Embed>"
            res = (res, out)

        else:
            if (isinstance(out, str) and
                    out.startswith("Traceback (most recent call last):\n")):
                # Leave out the traceback message
                out = "\n" + "\n".join(out.split("\n")[1:])

            pretty = (pprint.pformat(out, compact=True, width=60)
                      if not isinstance(out, str) else str(out))

            if pretty != str(out):
                # We're using the pretty version, start on the next line
                res += "\n"

            if pretty.count("\n") > 20:
                # Text too long, shorten
                li = pretty.split("\n")
                pretty = "\n".join(li[:3]) + "\n ...\n" + "\n".join(li[-3:])

            # Add the output
            res += pretty
            res = (res, None)

        return res

    async def _eval(self, ctx, code):
        self.ln += 1

        if code.startswith("exit"):
            self.ln = 0
            self.env = {}
            return await ctx.send(f"```Reset history!```")

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

        # Ignore this shitcode, it works
        _code = """
async def func():
    try:
        with contextlib.redirect_stdout(self.stdout):
{0}
        if '_' in locals():
            if inspect.isawaitable(_):
                _ = await _
            return _
    finally:
        self.env.update(locals())
""".format(textwrap.indent(code, '            '))

        try:
            exec(_code, self.env)  # noqa: B102 pylint: disable=exec-used
            func = self.env['func']
            res = await func()

        except:  # noqa pylint: disable=bare-except
            res = traceback.format_exc()

        out, embed = self._format(code, res)
        await ctx.send(f"```py\n{out}```", embed=embed)

    @command()
    @with_role(OWNER_ROLE)
    async def eval(self, ctx, *, code: str):
        """ Run eval in a REPL-like format. """
        code = code.strip("`")
        if code.startswith("py\n"):
            code = "\n".join(code.split("\n")[1:])

        if not re.search(  # Check if it's an expression
                r"^(return|import|for|while|def|class|"
                r"from|exit|[a-zA-Z0-9]+\s*=)", code, re.M) and len(
                    code.split("\n")) == 1:
            code = "_ = " + code

        await self._eval(ctx, code)


def setup(bot):
    bot.add_cog(EvalCog(bot))
    print("Cog loaded: Eval")
