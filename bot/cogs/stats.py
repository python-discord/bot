from discord import Member, Message, Status
from discord.ext.commands import Bot, Cog, Context


class Stats(Cog):
    """A cog which provides a way to hook onto Discord events and forward to stats."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Report message events in the server to statsd."""
        if message.guild is None:
            return

        reformatted_name = message.channel.name.replace('-', '_')

        if reformatted_name.startswith("ot"):
            # Off-topic channels change names, we don't want this for stats.
            # This will change 'ot1-lemon-in-the-dishwasher' to just 'ot1'
            reformatted_name = reformatted_name[:3]

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
        self.bot.stats.gauge(f"guild.total_members", len(member.guild.members))

    @Cog.listener()
    async def on_member_leave(self, member: Member) -> None:
        """Update member count stat on member leave."""
        self.bot.stats.gauge(f"guild.total_members", len(member.guild.members))

    @Cog.listener()
    async def on_member_update(self, _before: Member, after: Member) -> None:
        """Update presence estimates on member update."""
        members = after.guild.members

        online = len([m for m in members if m.status == Status.online])
        idle = len([m for m in members if m.status == Status.idle])
        dnd = len([m for m in members if m.status == Status.do_not_disturb])
        offline = len([m for m in members if m.status == Status.offline])

        self.bot.stats.gauge("guild.status.online", online)
        self.bot.stats.gauge("guild.status.idle", idle)
        self.bot.stats.gauge("guild.status.do_not_disturb", dnd)
        self.bot.stats.gauge("guild.status.offline", offline)


def setup(bot: Bot) -> None:
    """Load the stats cog."""
    bot.add_cog(Stats(bot))
