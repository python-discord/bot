from typing import Optional

import discord
from discord.ext import commands


class Context(commands.Context):
    async def send_error(self, error: Optional[str] = None, explanation: Optional[str] = None, *,
                         delete_after: Optional[float] = None):
        embed = discord.Embed(
            title=error,
            description=explanation,
            colour=discord.Colour.red()
        )
        return await self.send(embed=embed, delete_after=delete_after)
