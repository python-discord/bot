#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from io import BytesIO
from re import search


from aiohttp import ClientSession

from discord import File
from discord.ext.commands import command

from sympy import latex
from sympy.parsing.sympy_parser import parse_expr


LATEX_URL = "http://latex2png.com"


class Math:
    def __init__(self, bot):
        self.bot = bot

    @command()
    async def latexify(self, ctx, *, expr: str):
        fixed_expr = expr.replace('^', '**').strip('`').replace("__", "")
        try:
            parsed = parse_expr(fixed_expr, evaluate=False)

        except SyntaxError:
            await ctx.send("Invalid expression!")

        else:
            ltx = latex(parsed)

            data = {
                "latex": ltx,
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
        fixed_expr = expr.replace('^', '**').strip('`')

        if any(x in fixed_expr for x in ("**", "__")):
            return await ctx.send(
                "You used an expression that has been disabled for security, our apologies")


        try:
            parsed = parse_expr(fixed_expr, evaluate=False)
            result = parsed.doit()

        except SyntaxError:
            await ctx.send("Invalid expression!")

        else:
            ltx = latex(result)

            data = {
                "latex": ltx,
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
