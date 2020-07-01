from discord import TextChannel
from discord.ext.commands import Cog, Context, group

from bot.bot import Bot
from bot.constants import Emojis, MODERATION_ROLES
from bot.decorators import with_role


class Slowmode(Cog):

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @group(name='slowmode', aliases=['sm'], invoke_without_command=True)
    async def slowmode_group(self, ctx: Context) -> None:
        """Get and set the slowmode delay for a given text channel."""
        await ctx.send_help(ctx.command)

    @slowmode_group.command(name='get', aliases=['g'])
    async def get_slowmode(self, ctx: Context, channel: TextChannel) -> None:
        """Get the slowmode delay for a given text channel."""
        slowmode_delay = channel.slowmode_delay
        await ctx.send(f'The slowmode delay for {channel.mention} is {slowmode_delay} seconds.')

    @slowmode_group.command(name='set', aliases=['s'])
    @with_role(*MODERATION_ROLES)
    async def set_slowmode(self, ctx: Context, channel: TextChannel, seconds: int) -> None:
        """Set the slowmode delay for a given text channel."""
        await channel.edit(slowmode_delay=seconds)
        await ctx.send(
            f'{Emojis.check_mark} The slowmode delay for {channel.mention} is now {seconds} seconds.'
        )


def setup(bot: Bot) -> None:
    """Load the Slowmode cog."""
    bot.add_cog(Slowmode(bot))
