from collections import defaultdict

from discord import Status
from discord.ext.commands import Cog
from prometheus_client import Gauge

from bot.bot import Bot


class Metrics(Cog):
    """Exports metrics for Prometheus."""

    PREFIX = 'pydis_bot_'

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

        self.guild_members = Gauge(
            name=f'{self.PREFIX}server_members',
            documentation="Total members by status.",
            labelnames=('guild_id', 'status')
        )

    @Cog.listener()
    async def on_ready(self) -> None:
        members_by_status = defaultdict(lambda: defaultdict(int))

        for guild in self.bot.guilds:
            if guild.large:
                await self.bot.request_offline_members(guild)
            for member in guild.members:
                members_by_status[guild.id][member.status] += 1

        for guild_id, members in members_by_status.items():
            for status, count in members.items():
                self.guild_members.labels(guild_id=guild_id, status=str(status)).set(count)


def setup(bot: Bot) -> None:
    """Load the Metrics cog."""
    bot.add_cog(Metrics(bot))
