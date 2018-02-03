#!/usr/bin/env python3

import discord
from discord.ext import commands
import os

bot = commands.Bot(command_prefix=commands.when_mentioned_or(
    os.environ.get("BOT_PREFIX")))


@bot.command()
async def ping(ctx):
    await ctx.send("Pong.")

bot.run(os.environ.get("BOT_TOKEN"))
