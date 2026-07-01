from operator import itemgetter

import discord
from discord.ext import commands
from discord.ext.commands import BadArgument

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
        await self.bot.wait_until_guild_available()

        for channel_id in CHANNEL_IDS:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue

            last_message = channel.last_message
            if last_message is None:
                continue

            self.channel_id_to_timestamp[channel_id] = last_message.created_at.timestamp()

    @commands.command()
    async def tunnel(
        self,
        ctx: commands.Context,
        destination_channel: discord.TextChannel | None,
        source_channel: discord.TextChannel | None,
    ) -> None:
        """Creates a tunnel."""
        if ctx.guild is None:
            raise AssertionError

        if destination_channel is None:
            least_active_channel_id = self.get_least_active_channel_id(ctx.channel.id)
            least_active_channel = await ctx.guild.fetch_channel(least_active_channel_id)
            if not isinstance(least_active_channel, discord.TextChannel):
                raise AssertionError

            destination_channel = least_active_channel

        if source_channel is None:
            if not isinstance(ctx.channel, discord.TextChannel):
                raise BadArgument(
                    f"The current channel of type '{ctx.channel.type}' is not a valid source channel "
                    "and no explicit source channel was provided"
                )

            source_channel = ctx.channel

        if not isinstance(ctx.author, discord.Member):
            raise AssertionError

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
        channel_id, _ = min(
            [
                (channel_id, timestamp)
                for channel_id, timestamp in self.channel_id_to_timestamp.items()
                if channel_id != current_channel_id
            ],
            key=itemgetter(1),
        )
        return channel_id


async def setup(bot: Bot) -> None:
    """Load the Tunnel cog."""
    await bot.add_cog(Tunnel(bot))
