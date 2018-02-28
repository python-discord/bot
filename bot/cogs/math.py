#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from io import BytesIO
from urllib.parse import quote


from aiohttp import ClientSession

from discord import File
from discord.ext.commands import command

from sympy import latex
from sympy.parsing.sympy_parser import parse_expr


LATEX_URL = "https://latex.codecogs.com/png.download?%5Cdpi%7B150%7D%20%5Cbg_white%20%5Chuge%20"


class Math:
    def __init__(self, bot):
        self.bot = bot

    @command()
    async def latexify(self, ctx, *, expr: str):
        fixed_expr = expr.replace('^', '**')
        try:
            parsed = parse_expr(fixed_expr, evaluate=False)

        except SyntaxError:
            await ctx.send("Invalid expression!")

        else:
            ltx = latex(parsed)
            urlsafe = quote(ltx)

            async with ClientSession() as session:
                async with session.get(LATEX_URL + urlsafe) as resp:
                    bytes_img = await resp.read()

            file = File(fp=BytesIO(bytes_img), filename="latex.png")

            await ctx.send(file=file)


def setup(bot):
    bot.add_cog(Math(bot))
