import logging
from typing import Optional

from dateutil.relativedelta import relativedelta
from discord import TextChannel
from discord.ext.commands import Cog, Context, group, has_any_role

from bot.bot import Bot
from bot.constants import Channels, Emojis, MODERATION_ROLES
from bot.converters import DurationDelta
from bot.utils import time

log = logging.getLogger(__name__)

SLOWMODE_MAX_DELAY = 21600  # seconds

COMMONLY_SLOWMODED_CHANNELS = {
    Channels.python_general: "python_general",
    Channels.discord_py: "discordpy",
    Channels.off_topic_0: "ot0",
}


class Slowmode(Cog):
    """Commands for getting and setting slowmode delays of text channels."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @group(name='slowmode', aliases=['sm'], invoke_without_command=True)
    async def slowmode_group(self, ctx: Context) -> None:
        """Get or set the slowmode delay for the text channel this was invoked in or a given text channel."""
        await ctx.send_help(ctx.command)

    @slowmode_group.command(name='get', aliases=['g'])
    async def get_slowmode(self, ctx: Context, channel: Optional[TextChannel]) -> None:
        """Get the slowmode delay for a text channel."""
        # Use the channel this command was invoked in if one was not given
        if channel is None:
            channel = ctx.channel

        delay = relativedelta(seconds=channel.slowmode_delay)
        humanized_delay = time.humanize_delta(delay)

        await ctx.send(f'The slowmode delay for {channel.mention} is {humanized_delay}.')

    @slowmode_group.command(name='set', aliases=['s'])
    async def set_slowmode(self, ctx: Context, channel: Optional[TextChannel], delay: DurationDelta) -> None:
        """Set the slowmode delay for a text channel."""
        # Use the channel this command was invoked in if one was not given
        if channel is None:
            channel = ctx.channel

        # Convert `dateutil.relativedelta.relativedelta` to `datetime.timedelta`
        # Must do this to get the delta in a particular unit of time
        slowmode_delay = time.relativedelta_to_timedelta(delay).total_seconds()

        humanized_delay = time.humanize_delta(delay)

        # Ensure the delay is within discord's limits
        if slowmode_delay <= SLOWMODE_MAX_DELAY:
            log.info(f'{ctx.author} set the slowmode delay for #{channel} to {humanized_delay}.')

            await channel.edit(slowmode_delay=slowmode_delay)
            if channel.id in COMMONLY_SLOWMODED_CHANNELS:
                log.info(f'Recording slowmode change in stats for {channel.name}.')
                self.bot.stats.gauge(f"slowmode.{COMMONLY_SLOWMODED_CHANNELS[channel.id]}", slowmode_delay)

            await ctx.send(
                f'{Emojis.check_mark} The slowmode delay for {channel.mention} is now {humanized_delay}.'
            )

        else:
            log.info(
                f'{ctx.author} tried to set the slowmode delay of #{channel} to {humanized_delay}, '
                'which is not between 0 and 6 hours.'
            )

            await ctx.send(
                f'{Emojis.cross_mark} The slowmode delay must be between 0 and 6 hours.'
            )

    @slowmode_group.command(name='reset', aliases=['r'])
    async def reset_slowmode(self, ctx: Context, channel: Optional[TextChannel]) -> None:
        """Reset the slowmode delay for a text channel to 0 seconds."""
        await self.set_slowmode(ctx, channel, relativedelta(seconds=0))

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await has_any_role(*MODERATION_ROLES).predicate(ctx)


def setup(bot: Bot) -> None:
    """Load the Slowmode cog."""
    bot.add_cog(Slowmode(bot))
