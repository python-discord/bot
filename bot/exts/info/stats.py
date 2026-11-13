import string

from discord import Member, Message
from discord.ext.commands import Cog, Context
from discord.ext.tasks import loop

from bot.bot import Bot
from bot.constants import Categories, Channels, Guild
from bot.utils.channel import is_in_category

CHANNEL_NAME_OVERRIDES = {
    Channels.off_topic_0: "off_topic_0",
    Channels.off_topic_1: "off_topic_1",
    Channels.off_topic_2: "off_topic_2",
    Channels.staff_lounge: "staff_lounge"
}

ALLOWED_CHARS = string.ascii_letters + string.digits + "_"


class Stats(Cog):
    """A cog which provides a way to hook onto Discord events and forward to stats."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.last_presence_update = None
        self.update_guild_boost.start()

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Report message events in the server to statsd."""
        if message.guild is None:
            return

        if message.guild.id != Guild.id:
            return

        if is_in_category(message.channel, Categories.modmail):
            if message.channel.id != Channels.incidents:
                # Do not report modmail channels to stats, there are too many
                # of them for interesting statistics to be drawn out of this.
                return

        channel = message.channel
        if hasattr(channel, "parent") and channel.parent:
            channel = channel.parent
        reformatted_name = CHANNEL_NAME_OVERRIDES.get(channel.id, channel.name)
        reformatted_name = "".join(char if char in ALLOWED_CHARS else "_" for char in reformatted_name)

        stat_name = f"channels.{reformatted_name}"
        self.bot.stats.incr(stat_name)

        # Increment the total message count
        self.bot.stats.incr("messages")

    @Cog.listener()
    async def on_command_completion(self, ctx: Context) -> None:
        """Report completed commands to statsd."""
        command_name = ctx.command.qualified_name.replace(" ", "_")

        self.bot.stats.incr(f"commands.{command_name}")

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """Update member count stat on member join."""
        if member.guild.id != Guild.id:
            return

        self.bot.stats.gauge("guild.total_members", len(member.guild.members))

    @Cog.listener()
    async def on_member_leave(self, member: Member) -> None:
        """Update member count stat on member leave."""
        if member.guild.id != Guild.id:
            return

        self.bot.stats.gauge("guild.total_members", len(member.guild.members))

    @loop(hours=1)
    async def update_guild_boost(self) -> None:
        """Post the server boost level and tier every hour."""
        await self.bot.wait_until_guild_available()
        g = self.bot.get_guild(Guild.id)
        self.bot.stats.gauge("boost.amount", g.premium_subscription_count)
        self.bot.stats.gauge("boost.tier", g.premium_tier)

    async def cog_unload(self) -> None:
        """Stop the boost statistic task on unload of the Cog."""
        self.update_guild_boost.stop()


async def setup(bot: Bot) -> None:
    """Load the stats cog."""
    await bot.add_cog(Stats(bot))
