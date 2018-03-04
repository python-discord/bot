#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys
from contextlib import suppress
from io import BytesIO
from re import search
from subprocess import PIPE, Popen, STDOUT, TimeoutExpired  # noqa: B404

from aiohttp import ClientSession

from discord import File
from discord.ext.commands import command


LATEX_URL = "https://latex2png.com"


async def run_sympy(sympy_code: str, calc: bool = False, timeout: int = 10) -> str:
    if calc:
        code_ = "parse_expr(sys.argv[1]).doit()"
    else:
        code_ = "parse_expr(sys.argv[1], evaluate=True)"

    if "__" in sympy_code:
        raise TypeError("'__' not allowed in sympy code")

    proc = Popen([sys.executable, "-c",
                  "import sys,sympy;from sympy.parsing.sympy_parser import parse_expr;"
                  f"print(sympy.latex({code_}))", sympy_code],
                 stdout=PIPE, stderr=STDOUT)  # noqa: B603

    for _ in range(timeout*4):
        await asyncio.sleep(1/4)
        with suppress(TimeoutExpired):
            proc.wait(0)
            break

    proc.kill()
    return proc.returncode, proc.stdout.read().decode().strip()


class Math:
    def __init__(self, bot):
        self.bot = bot

    @command()
    async def latexify(self, ctx, *, expr: str):
        """
        Return the LaTex output for a mathematical expression
        """

        fixed_expr = expr.replace('^', '**').strip('`')
        try:
            retcode, parsed = await run_sympy(fixed_expr) 

        except TypeError as e:
            await ctx.send(e.args[0])

        else:
            if retcode != 0:
                await ctx.send(f"Error:\n```{parsed}```")
                return
            elif not parsed:
                await ctx.send("Code did not return or took too long")
                return

            data = {
                "latex": parsed,
                "res": 300,
                "color": 808080
            }

            async with ClientSession() as session:
                async with session.post(LATEX_URL, data=data) as resp:
                    html = await resp.text()

                name = search(r'hist\.request\.basename = "(?P<url>[^"]+)"', html).group('url')

                async with session.get(f"{LATEX_URL}/output/{name}.png") as resp:
                    bytes_img = await resp.read()

            file = File(fp=BytesIO(bytes_img), filename="latex.png")

            await ctx.send(file=file)

    @command()
    async def calc(self, ctx, *, expr: str):
        """
        Return the LaTex output for the solution to a mathematical expression
        """

        fixed_expr = expr.replace('^', '**').strip('`')
        try:
            retcode, parsed = await run_sympy(fixed_expr, calc=True) 

        except TypeError as e:
            await ctx.send(e.args[0])

        else:
            if retcode != 0:
                await ctx.send(f"Error:\n```{parsed}```")
                return
            elif not parsed:
                await ctx.send("Code did not return or took too long")
                return

            data = {
                "latex": parsed,
                "res": 300,
                "color": 808080
            }

            async with ClientSession() as session:
                async with session.post(LATEX_URL, data=data) as resp:
                    html = await resp.text()

                name = search(r'hist\.request\.basename = "(?P<url>[^"]+)"', html).group('url')

                async with session.get(f"{LATEX_URL}/output/{name}.png") as resp:
                    bytes_img = await resp.read()

            file = File(fp=BytesIO(bytes_img), filename="latex.png")

            await ctx.send(file=file)


def setup(bot):
    bot.add_cog(Math(bot))
