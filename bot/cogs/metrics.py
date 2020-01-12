from collections import defaultdict

from discord import Member, Message
from discord.ext.commands import Cog
from prometheus_client import Counter, Gauge

from bot.bot import Bot


class Metrics(Cog):
    """
    Exports metrics for Prometheus.

    See https://github.com/prometheus/client_python for metric documentation.
    """

    PREFIX = 'pydis_bot'

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

        self.guild_members = Gauge(
            name=f'{self.PREFIX}_guild_members',
            documentation="Total members by guild by status.",
            labelnames=('guild_id', 'status')
        )
        self.guild_messages = Counter(
            name=f'{self.PREFIX}_guild_messages',
            documentation="Guild messages by guild by channel.",
            labelnames=('channel_id', 'guild_id', 'channel_name')
        )

    @Cog.listener()
    async def on_ready(self) -> None:
        """Initialize the guild member counter."""
        members_by_status = defaultdict(lambda: defaultdict(int))

        for guild in self.bot.guilds:
            if guild.large:
                await self.bot.request_offline_members(guild)
            for member in guild.members:
                members_by_status[guild.id][member.status] += 1

        for guild_id, members in members_by_status.items():
            for status, count in members.items():
                self.guild_members.labels(guild_id=guild_id, status=str(status)).set(count)

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """Increment the member gauge."""
        self.guild_members.labels(guild_id=member.guild.id, status=str(member.status)).inc()

    @Cog.listener()
    async def on_member_leave(self, member: Member) -> None:
        """Decrement the member gauge."""
        self.guild_members.labels(guild_id=member.guild.id, status=str(member.status)).dec()

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member) -> None:
        """Update member gauges for the new and old status if applicable."""
        if before.status is not after.status:
            self.guild_members.labels(guild_id=after.guild.id, status=str(before.status)).dec()
            self.guild_members.labels(guild_id=after.guild.id, status=str(after.status)).inc()

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Increment the guild message counter."""
        self.guild_messages.labels(
            channel_id=message.channel.id,
            channel_name=message.channel.name,
            guild_id=message.guild.id,
        ).inc()


def setup(bot: Bot) -> None:
    """Load the Metrics cog."""
    bot.add_cog(Metrics(bot))
