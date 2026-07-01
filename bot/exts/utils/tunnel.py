import discord
from discord.ext import commands
from discord.ext.commands import BadArgument, guild_only

from bot.bot import Bot
from bot.constants import Channels

CHANNEL_IDS = (Channels.off_topic_0, Channels.off_topic_1, Channels.off_topic_2)


class Tunnel(commands.Cog):
    """Enables conversation redirection between channels."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.channel_id_to_timestamp: dict[int, float] = dict.fromkeys(CHANNEL_IDS, 0)

    async def cog_load(self) -> None:
        """Initialize channel timestamps."""
        for channel_id in CHANNEL_IDS:
            channel = await self.bot.fetch_channel(channel_id)
            if channel is None:
                continue

            last_message_id = channel.last_message_id
            if last_message_id is None:
                continue

            last_message = await channel.fetch_message(last_message_id)
            if last_message is None:
                continue

            self.channel_id_to_timestamp[channel_id] = last_message.created_at.timestamp()

    @commands.command()
    @guild_only()
    async def tunnel(
        self,
        ctx: commands.Context,
        destination_channel: discord.TextChannel | None,
    ) -> None:
        """Creates a tunnel."""
        if destination_channel is None:
            least_active_channel_id = self.get_least_active_channel_id(ctx.channel.id)
            least_active_channel = await ctx.guild.fetch_channel(least_active_channel_id)
            destination_channel = least_active_channel

        source_channel = ctx.channel

        if not source_channel.permissions_for(ctx.author).send_messages:
            raise BadArgument(f"You don't have permission to send messages in {source_channel.jump_url}")
        if not destination_channel.permissions_for(ctx.author).send_messages:
            raise BadArgument(f"You don't have permission to send messages in {destination_channel.jump_url}")

        if source_channel.id == destination_channel.id:
            raise BadArgument("Source and destination channels cannot be the same")

        source_message_template = "➡️ Conversation tunneled to {location}"
        destination_message_template = "↩️ Conversation tunneled from {location}"

        source_message = await source_channel.send(
            content=source_message_template.format(location=destination_channel.jump_url)
        )
        destination_message = await destination_channel.send(
            content=destination_message_template.format(location=source_message.jump_url)
        )
        await source_message.edit(content=source_message_template.format(location=destination_message.jump_url))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Determines least active off-topic channel to default to."""
        if message.channel.id not in CHANNEL_IDS:
            return

        self.channel_id_to_timestamp[message.channel.id] = message.created_at.timestamp()

    def get_least_active_channel_id(self, current_channel_id: int) -> int:
        """Gets least active off-topic channel."""
        return min(
            (channel for channel in self.channel_id_to_timestamp if channel != current_channel_id),
            key=lambda c: self.channel_id_to_timestamp[c]
        )


async def setup(bot: Bot) -> None:
    """Load the Tunnel cog."""
    await bot.add_cog(Tunnel(bot))
