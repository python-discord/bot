import string
from datetime import datetime

from discord import Member, Message, Status
from discord.ext.commands import Bot, Cog, Context

from bot.constants import Channels, Guild, Stats as StatConf


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

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Report message events in the server to statsd."""
        if message.guild is None:
            return

        if message.guild.id != Guild.id:
            return

        reformatted_name = message.channel.name.replace('-', '_')

        if CHANNEL_NAME_OVERRIDES.get(message.channel.id):
            reformatted_name = CHANNEL_NAME_OVERRIDES.get(message.channel.id)

        reformatted_name = "".join(char for char in reformatted_name if char in ALLOWED_CHARS)

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

        self.bot.stats.gauge(f"guild.total_members", len(member.guild.members))

    @Cog.listener()
    async def on_member_leave(self, member: Member) -> None:
        """Update member count stat on member leave."""
        if member.guild.id != Guild.id:
            return

        self.bot.stats.gauge(f"guild.total_members", len(member.guild.members))

    @Cog.listener()
    async def on_member_update(self, _before: Member, after: Member) -> None:
        """Update presence estimates on member update."""
        if after.guild.id != Guild.id:
            return

        if self.last_presence_update:
            if (datetime.now() - self.last_presence_update).seconds < StatConf.presence_update_timeout:
                return

        self.last_presence_update = datetime.now()

        online = 0
        idle = 0
        dnd = 0
        offline = 0

        for member in after.guild.members:
            if member.status is Status.online:
                online += 1
            elif member.status is Status.dnd:
                dnd += 1
            elif member.status is Status.idle:
                idle += 1
            elif member.status is Status.offline:
                offline += 1

        self.bot.stats.gauge("guild.status.online", online)
        self.bot.stats.gauge("guild.status.idle", idle)
        self.bot.stats.gauge("guild.status.do_not_disturb", dnd)
        self.bot.stats.gauge("guild.status.offline", offline)


def setup(bot: Bot) -> None:
    """Load the stats cog."""
    bot.add_cog(Stats(bot))
