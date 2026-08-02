import discord
from discord.ext import commands
from discord.ext.commands import BadArgument, guild_only

from bot.bot import Bot
from bot.constants import Channels

CHANNEL_IDS: tuple[int, ...] = (Channels.off_topic_0, Channels.off_topic_1, Channels.off_topic_2)


class Tunnel(commands.Cog):
    """Enables conversation redirection between channels."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.channels: list[discord.TextChannel] = []

    async def cog_load(self) -> None:
        """Initialize channel timestamps."""
        self.channels = []
        for channel_id in CHANNEL_IDS:
            channel = await self.bot.fetch_channel(channel_id)
            if channel is None:
                continue

            self.channels.append(channel)

    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.command()
    @guild_only()
    async def tunnel(
        self,
        ctx: commands.Context,
        destination_channel_raw: str | None,
    ) -> None:
        """Creates a tunnel."""
        if destination_channel_raw is None:
            least_active_channel = self.get_least_active_channel(ctx.channel)
            destination_channel = least_active_channel
        else:
            destination_channel = await commands.TextChannelConverter().convert(ctx, destination_channel_raw)

        source_channel = ctx.channel

        if not source_channel.permissions_for(ctx.author).send_messages:
            raise BadArgument(f"You don't have permission to send messages in {source_channel.jump_url}")
        if not destination_channel.permissions_for(ctx.author).send_messages:
            raise BadArgument(f"You don't have permission to send messages in {destination_channel.jump_url}")

        if source_channel.id == destination_channel.id:
            raise BadArgument("Source and destination channels cannot be the same")

        source_message_template = f"➡️ Conversation continued at {{location}} (by <@{ctx.author.id}>)"
        destination_message_template = f"↩️ Conversation continued from {{location}} (by <@{ctx.author.id}>)"

        source_message = await source_channel.send(
            content=source_message_template.format(location=destination_channel.jump_url)
        )
        destination_message = await destination_channel.send(
            content=destination_message_template.format(location=source_message.jump_url)
        )
        await source_message.edit(content=source_message_template.format(location=destination_message.jump_url))

    def get_least_active_channel(self, current_channel: discord.TextChannel) -> discord.TextChannel:
        """Gets least active off-topic channel."""
        return min(
            (c for c in self.channels if c != current_channel),
            key=lambda c: discord.utils.snowflake_time(c.last_message_id),
        )


async def setup(bot: Bot) -> None:
    """Load the Tunnel cog."""
    await bot.add_cog(Tunnel(bot))
