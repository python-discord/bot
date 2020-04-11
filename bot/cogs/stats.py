from discord import Member, Message, Status
from discord.ext.commands import Bot, Cog, Context

from bot.constants import Guild


CHANNEL_NAME_OVERRIDES = {
    Guild.channels.off_topic_0: "off_topic_0",
    Guild.channels.off_topic_1: "off_topic_1",
    Guild.channels.off_topic_2: "off_topic_2",
    Guild.channels.staff_lounge: "staff_lounge"
}


class Stats(Cog):
    """A cog which provides a way to hook onto Discord events and forward to stats."""

    def __init__(self, bot: Bot):
        self.bot = bot

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

        online = 0
        idle = 0
        dnd = 0
        offline = 0

        for member in after.guild.members:
            if member.status == Status.online:
                online += 1
            elif member.status == Status.dnd:
                dnd += 1
            elif member.status == Status.idle:
                idle += 1
            else:
                offline += 1

        self.bot.stats.gauge("guild.status.online", online)
        self.bot.stats.gauge("guild.status.idle", idle)
        self.bot.stats.gauge("guild.status.do_not_disturb", dnd)
        self.bot.stats.gauge("guild.status.offline", offline)


def setup(bot: Bot) -> None:
    """Load the stats cog."""
    bot.add_cog(Stats(bot))
