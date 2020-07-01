import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta
from discord import TextChannel
from discord.ext.commands import Cog, Context, group

from bot.bot import Bot
from bot.constants import Emojis, MODERATION_ROLES
from bot.converters import DurationDelta
from bot.decorators import with_role
from bot.utils import time

log = logging.getLogger(__name__)


class Slowmode(Cog):
    """Commands for getting and setting slowmode delays of text channels."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @group(name='slowmode', aliases=['sm'], invoke_without_command=True)
    async def slowmode_group(self, ctx: Context) -> None:
        """Get and set the slowmode delay for a given text channel."""
        await ctx.send_help(ctx.command)

    @slowmode_group.command(name='get', aliases=['g'])
    async def get_slowmode(self, ctx: Context, channel: TextChannel) -> None:
        """Get the slowmode delay for a given text channel."""
        delay = relativedelta(seconds=channel.slowmode_delay)

        try:
            humanized_delay = time.humanize_delta(delay, precision=3)

        except TypeError:
            # The slowmode delay is 0 seconds,
            # which causes `time.humanize_delta` to raise a TypeError
            humanized_delay = '0 seconds'

        finally:
            await ctx.send(f'The slowmode delay for {channel.mention} is {humanized_delay}.')

    @slowmode_group.command(name='set', aliases=['s'])
    @with_role(*MODERATION_ROLES)
    async def set_slowmode(self, ctx: Context, channel: TextChannel, delay: DurationDelta) -> None:
        """Set the slowmode delay for a given text channel."""
        # Convert `dateutil.relativedelta.relativedelta` to `datetime.timedelta`
        # Must do this to get the delta in a particular unit of time
        utcnow = datetime.utcnow()
        slowmode_delay = (utcnow + delay - utcnow).total_seconds()

        humanized_delay = time.humanize_delta(delay, precision=3)

        if 0 <= slowmode_delay <= 21600:
            await channel.edit(slowmode_delay=slowmode_delay)
            await ctx.send(
                f'{Emojis.check_mark} The slowmode delay for {channel.mention} is now {humanized_delay}.'
            )

            log.info(f'{ctx.author} set the slowmode delay for #{channel} to {humanized_delay}.')

        else:
            await ctx.send(
                f'{Emojis.cross_mark} The slowmode delay must be between 0 and 6 hours.'
            )
            log.info(
                f'{ctx.author} tried to set the slowmode delay of #{channel} to {humanized_delay}, '
                'which is not between 0 and 6 hours.'
            )

    @slowmode_group.command(name='reset', aliases=['r'])
    @with_role(*MODERATION_ROLES)
    async def reset_slowmode(self, ctx: Context, channel: TextChannel) -> None:
        """Reset the slowmode delay for a given text channel to 0 seconds."""
        await channel.edit(slowmode_delay=0)
        await ctx.send(
            f'{Emojis.check_mark} The slowmode delay for {channel.mention} has been reset to 0 seconds.'
        )
        log.info(f'{ctx.author} reset the slowmode delay for #{channel} to 0 seconds.')


def setup(bot: Bot) -> None:
    """Load the Slowmode cog."""
    bot.add_cog(Slowmode(bot))
