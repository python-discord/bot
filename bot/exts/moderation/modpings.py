import datetime
import logging

from discord import Embed
from discord.ext.commands import Cog, Context, group, has_any_role

from bot.bot import Bot
from bot.constants import Colours, Emojis, Guild, Icons, MODERATION_ROLES, Roles
from bot.converters import Expiry
from bot.utils.persistent_scheduling import PersistentScheduler

log = logging.getLogger(__name__)


class ModPings(Cog):
    """Commands for a moderator to turn moderator pings on and off."""

    def __init__(self, bot: Bot):
        self.bot = bot

        self.guild = None
        self.moderators_role = None

        self.start_task = self.bot.loop.create_task(self.start_cog(), name="mod-pings-start")
        self._role_scheduler = PersistentScheduler(self.__class__.__name__, self.reapply_role, bot.loop)
        self.reschedule_task = self.bot.loop.create_task(self.normalize_roles(), name="mod-pings-reschedule")

    async def start_cog(self) -> None:
        """Sets the guild related attributes to use in the cog."""
        await self.bot.wait_until_guild_available()
        self.guild = self.bot.get_guild(Guild.id)
        self.moderators_role = self.guild.get_role(Roles.moderators)

    async def normalize_roles(self) -> None:
        """Reschedule moderators role re-apply times."""
        await self.start_task

        await self._role_scheduler.wait_until_ready()

        mod_team = self.guild.get_role(Roles.mod_team)
        pings_on = self.moderators_role.members

        log.trace("Applying the moderators role to the mod team where necessary.")
        for mod in mod_team.members:
            if mod in pings_on:  # Make sure that on-duty mods aren't in the cache.
                if mod.id in self._role_scheduler:
                    await self._role_scheduler.delete(mod.id)

            # Keep the role off only for those in the cache.
            elif mod.id not in self._role_scheduler:
                await self.reapply_role(mod.id)

    async def reapply_role(self, mod_id: int) -> None:
        """Reapply the moderator's role to the given moderator."""
        log.trace(f"Re-applying role to mod with ID {mod_id}.")
        await self.start_task
        mod = self.guild.get_member(mod_id)
        await mod.add_roles(self.moderators_role, reason="Pings off period expired.")

    @group(name='modpings', aliases=('modping',), invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def modpings_group(self, ctx: Context) -> None:
        """Allow the removal and re-addition of the pingable moderators role."""
        await ctx.send_help(ctx.command)

    @modpings_group.command(name='off')
    @has_any_role(*MODERATION_ROLES)
    async def off_command(self, ctx: Context, duration: Expiry) -> None:
        """
        Temporarily removes the pingable moderators role for a set amount of time.

        A unit of time should be appended to the duration.
        Units (∗case-sensitive):
        \u2003`y` - years
        \u2003`m` - months∗
        \u2003`w` - weeks
        \u2003`d` - days
        \u2003`h` - hours
        \u2003`M` - minutes∗
        \u2003`s` - seconds

        Alternatively, an ISO 8601 timestamp can be provided for the duration.

        The duration cannot be longer than 30 days.
        """
        duration: datetime.datetime
        delta = duration - datetime.datetime.utcnow()
        if delta > datetime.timedelta(days=30):
            await ctx.send(":x: Cannot remove the role for longer than 30 days.")
            return

        mod = ctx.author

        until_date = duration.replace(microsecond=0).isoformat()  # Looks noisy with microseconds.
        await mod.remove_roles(self.moderators_role, reason=f"Turned pings off until {until_date}.")

        # Allow rescheduling the task without cancelling it separately via the `on` command.
        if mod.id in self._role_scheduler:
            self._role_scheduler.cancel(mod.id)
        await self._role_scheduler.schedule_at(duration, mod.id)

        embed = Embed(timestamp=duration, colour=Colours.bright_green)
        embed.set_footer(text="Moderators role has been removed until", icon_url=Icons.green_checkmark)
        await ctx.send(embed=embed)

    @modpings_group.command(name='on')
    @has_any_role(*MODERATION_ROLES)
    async def on_command(self, ctx: Context) -> None:
        """Re-apply the pingable moderators role."""
        mod = ctx.author
        if mod in self.moderators_role.members:
            await ctx.send(":question: You already have the role.")
            return

        await mod.add_roles(self.moderators_role, reason="Pings off period canceled.")

        await self._role_scheduler.delete(mod.id)

        await ctx.send(f"{Emojis.check_mark} Moderators role has been re-applied.")

    def cog_unload(self) -> None:
        """Cancel tasks when the cog unloads."""
        log.trace("Cog unload: canceling role tasks.")
        self.start_task.cancel()
        self.reschedule_task.cancel()
        self._role_scheduler.cancel_all()


def setup(bot: Bot) -> None:
    """Load the ModPings cog."""
    bot.add_cog(ModPings(bot))
