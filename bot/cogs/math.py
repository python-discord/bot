#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import sys
from contextlib import suppress
from io import BytesIO
from re import finditer
from subprocess import PIPE, Popen, STDOUT, TimeoutExpired  # noqa: B404 S404
from urllib.parse import quote

from discord import File
from discord.ext.commands import command

\documentclass{article}\usepackage[utf8]{inputenc}\usepackage{amsfonts}\usepackage{amssymb}\usepackage{mathrsfs}\usepackage{chemfig}\usepackage[siunitx, american]{circuitikz}\usepackage{mathtools}\usepackage{mhchem}\usepackage{tikz-cd}\usepackage{color}\usepackage{xcolor}\usepackage{cancel}\usepackage[a5paper]{geometry}\usepackage{dsfont}\newfam\hebfam\font\tmp=rcjhbltx at10pt \textfont\hebfam=\tmp\font\tmp=rcjhbltx at7pt  \scriptfont\hebfam=\tmp\font\tmp=rcjhbltx at5pt  \scriptscriptfont\hebfam=\tmp\edef\declfam{\ifcase\hebfam 0\or1\or2\or3\or4\or5\or6\or7\or8\or9\or A\or B\or C\or D\or E\or F\fi}\mathchardef\shin   = "0\declfam 98\mathchardef\aleph  = "0\declfam 27\mathchardef\beth   = "0\declfam 62\mathchardef\gimel  = "0\declfam 67\mathchardef\daleth = "0\declfam 64\mathchardef\ayin   = "0\declfam 60\mathchardef\tsadi  = "0\declfam 76\mathchardef\qof    = "0\declfam 72\mathchardef\lamed  = "0\declfam 6C\mathchardef\mim    = "0\declfam 6D\newcommand{\bbR}{\mathbb{R}}\newcommand{\bbQ}{\mathbb{Q}}\newcommand{\bbC}{\mathbb{C}}\newcommand{\bbZ}{\mathbb{Z}}\newcommand{\bbN}{\mathbb{N}}\newcommand{\bbH}{\mathbb{H}}\newcommand{\bbK}{\mathbb{K}}\newcommand{\bbG}{\mathbb{G}}\newcommand{\bbP}{\mathbb{P}}\newcommand{\bbX}{\mathbb{X}}\newcommand{\bbD}{\mathbb{D}}\newcommand{\bbO}{\mathbb{O}}\newcommand{\bigO}{\mathcal{O}}\newcommand{\ceil}[1]{\left\lceil{#1}\right\rceil}\newcommand{\floor}[1]{\left\lfloor{#1}\right\rfloor}\begin{document}\pagenumbering{gobble}\definecolor{my_colour}{HTML}{7289DA}\color{my_colour}\begin{flushleft}CONTENT\end{flushleft}\end{document}

log = logging.getLogger(__name__)
LATEX_URL = "http://rtex.probablyaweb.site/api/v2"

def ropen(filename, *args, **kwargs):
    codefile = inspect.stack()[1].filename
    abspath = os.path.abspath(codefile)
    directory = os.path.dirname(abspath)
    path = os.path.join(directory, filename)
    return open(path, *args, **kwargs)

with ropen("base.tex") as f:
    LATEX_BASE = f.read()

async def run_sympy(sympy_code: str, calc: bool = False, timeout: int = 10) -> tuple:
    if calc:
        code_ = "parse_expr(sys.argv[1]).doit()"  # Run the expression
    else:
        code_ = "parse_expr(sys.argv[1], evaluate=True)"  # Just latexify it without running

    if "__" in sympy_code:
        # They're trying to exploit something, raise an error
        raise TypeError("'__' not allowed in sympy code")

    log.info(f"Running expression (Will eval: {calc}")

    proc = Popen([  # noqa: B603 S603
                    sys.executable, "-c",
                    "import sys,sympy;from sympy.parsing.sympy_parser import parse_expr;"
                    f"print(sympy.latex({code_}))", sympy_code
                 ], env={},  # Disable environment variables for security
                 stdout=PIPE, stderr=STDOUT)  # reroute all to stdout

    log.debug("Waiting for process to end...")

    for _ in range(timeout*4):  # Check if done every .25 seconds for `timeout` seconds
        await asyncio.sleep(1/4)

        # Ignore TimeoutExpired...
        with suppress(TimeoutExpired):
            proc.wait(0)
            break  # ... But stop the loop when not raised
    else:
        log.warn("Calculation forcibly stopped for taking too long!")

    proc.kill()  # Kill the process regardless of whether it finished or not
    return proc.returncode, proc.stdout.read().decode().strip()


class Math:
    latex_regexp = r"\$(?P<lim>`{1,2})(?P<latex>.+?[^\\])(?P=lim)"

    def __init__(self, bot):
        self.bot = bot

    async def download_latex(self, latex: str) -> File:
        log.info("Downloading latex from 'API'")

        async with self.bot.http_session as session:
            async with session.post(LATEX_URL, json={"code": LATEX_BASE.replace("CONTENT", latex), "format": "png"}) as resp:
                data = await resp.json()

            log.debug(json.dumps(data))

            async with session.get(f"{LATEX_URL}/{data['filename']}") as resp:
                bytes_img = await resp.read()

        return File(fp=BytesIO(bytes_img), filename="latex.png")

    async def on_message(self, message):
        """Parser for LaTeX
        Checks for any $`...` or $``...`` in a message,
        and uploads the rendered images
        """
        files = []
        for match in finditer(self.latex_regexp, message.content):
            latex = match.group('latex')
            files.append(
                await self.download_latex(latex)
            )

        if files:
            log.info("Latex expressions found in message, uploading...")
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
            file = await self.download_latex(parsed)

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
            file = await self.download_latex(parsed)

            await ctx.send(file=file)


def setup(bot):
    bot.add_cog(Math(bot))
