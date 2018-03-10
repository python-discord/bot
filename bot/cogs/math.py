#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys
from contextlib import suppress
from io import BytesIO
from re import finditer, search
from subprocess import PIPE, Popen, STDOUT, TimeoutExpired  # noqa: B404

from aiohttp import ClientSession
from discord import File
from discord.ext.commands import command


LATEX_URL = "https://latex2png.com"


async def run_sympy(sympy_code: str, calc: bool = False, timeout: int = 10) -> tuple:
    if calc:
        code_ = "parse_expr(sys.argv[1]).doit()"  # Run the expression
    else:
        code_ = "parse_expr(sys.argv[1], evaluate=True)"  # Just latexify it without running

    if "__" in sympy_code:
        # They're trying to exploit something, raise an error
        raise TypeError("'__' not allowed in sympy code")

    proc = Popen([  # noqa: B603
                    sys.executable, "-c",
                    "import sys,sympy;from sympy.parsing.sympy_parser import parse_expr;"
                    f"print(sympy.latex({code_}))", sympy_code
                 ], env={},  # Disable environment variables for security
                 stdout=PIPE, stderr=STDOUT)  # reroute all to stdout

    for _ in range(timeout*4):  # Check if done every .25 seconds for `timeout` seconds
        await asyncio.sleep(1/4)

        # Ignore TimeoutExpired...
        with suppress(TimeoutExpired):
            proc.wait(0)
            break  # ... But stop the loop when not raised

    proc.kill()  # Kill the process regardless of whether it finished or not
    return proc.returncode, proc.stdout.read().decode().strip()


async def download_latex(latex: str) -> File:
    data = {
        "latex": latex,
        "res": 300,
        "color": 808080
    }

    async with ClientSession() as session:
        async with session.post(LATEX_URL, data=data) as resp:
            html = await resp.text()

        name = search(r'hist\.request\.basename = "(?P<url>[^"]+)"', html).group('url')

        async with session.get(f"{LATEX_URL}/output/{name}.png") as resp:
            bytes_img = await resp.read()

    return File(fp=BytesIO(bytes_img), filename="latex.png")


class Math:
    latex_regexp = r"\$(?P<lim>`{1,2})(?P<latex>.+?[^\\])(?P=lim)"

    def __init__(self, bot):
        self.bot = bot

    async def on_message(self, message):
        """Parser for LaTeX
        Checks for any $`...` or $``...`` in a message,
        and uploads the rendered images
        """
        files = []
        for match in finditer(self.latex_regexp, message.content):
            latex = match.group('latex')
            files.append(
                await download_latex(latex)
            )

        if files:
            await message.channel.send(files=files)

    @command()
    async def latexify(self, ctx, *, expr: str):
        """
        Return the LaTeX output for a mathematical expression
        """

        fixed_expr = expr.replace('^', '**').strip('`')  # Syntax fixes
        try:
            retcode, parsed = await run_sympy(fixed_expr)  # Run the sympy code

        except TypeError as e:  # Exploit was tried
            await ctx.send(e.args[0])

        else:
            if retcode != 0:  # ERROR
                await ctx.send(f"Error:\n```{parsed}```")
                return
            elif not parsed:  # Timeout
                await ctx.send("Code did not return or took too long")
                return

            # Send LaTeX to website to get image
            file = await download_latex(parsed)

            await ctx.send(file=file)

    @command()
    async def calc(self, ctx, *, expr: str):
        """
        Return the LaTeX output for the solution to a mathematical expression
        """

        fixed_expr = expr.replace('^', '**').strip('`')  # Syntax fixes
        try:
            retcode, parsed = await run_sympy(fixed_expr, calc=True)  # Run sympy

        except TypeError as e:  # Exploitation tried
            await ctx.send(e.args[0])

        else:
            if retcode != 0:  # ERROR
                await ctx.send(f"Error:\n```{parsed}```")
                return
            elif not parsed:  # Timeout
                await ctx.send("Code did not return or took too long")
                return

            # Send LaTeX to website to get image
            file = await download_latex(parsed)

            await ctx.send(file=file)


def setup(bot):
    bot.add_cog(Math(bot))
