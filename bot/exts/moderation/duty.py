import datetime
import logging

from async_rediscache import RedisCache
from dateutil.parser import isoparse
from discord import Member
from discord.ext.commands import Cog, Context, group, has_any_role

from bot.bot import Bot
from bot.constants import Emojis, Guild, MODERATION_ROLES, Roles
from bot.converters import Expiry
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)


class Duty(Cog):
    """Commands for a moderator to go on and off duty."""

    # RedisCache[str, str]
    # The cache's keys are mods who are off-duty.
    # The cache's values are the times when the role should be re-applied to them, stored in ISO format.
    off_duty_mods = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self._role_scheduler = Scheduler(self.__class__.__name__)

        self.guild = None
        self.moderators_role = None

        self.bot.loop.create_task(self.reschedule_roles())

    async def reschedule_roles(self) -> None:
        """Reschedule moderators role re-apply times."""
        await self.bot.wait_until_guild_available()
        self.guild = self.bot.get_guild(Guild.id)
        self.moderators_role = self.guild.get_role(Roles.moderators)

        mod_team = self.guild.get_role(Roles.mod_team)
        on_duty = self.moderators_role.members
        off_duty = await self.off_duty_mods.to_dict()

        log.trace("Applying the moderators role to the mod team where necessary.")
        for mod in mod_team.members:
            if mod in on_duty:  # Make sure that on-duty mods aren't in the cache.
                if mod in off_duty:
                    await self.off_duty_mods.delete(mod.id)
                continue

            # Keep the role off only for those in the cache.
            if mod.id not in off_duty:
                await self.reapply_role(mod)
            else:
                expiry = isoparse(off_duty[mod.id]).replace(tzinfo=None)
                self._role_scheduler.schedule_at(expiry, mod.id, self.reapply_role(mod))

    async def reapply_role(self, mod: Member) -> None:
        """Reapply the moderator's role to the given moderator."""
        log.trace(f"Re-applying role to mod with ID {mod.id}.")
        await mod.add_roles(self.moderators_role, reason="Off-duty period expired.")

    @group(name='duty', invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def duty_group(self, ctx: Context) -> None:
        """Allow the removal and re-addition of the pingable moderators role."""
        await ctx.send_help(ctx.command)

    @duty_group.command(name='off')
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
        await mod.remove_roles(self.moderators_role, reason=f"Entered off-duty period until {until_date}.")

        await self.off_duty_mods.set(mod.id, duration.isoformat())

        # Allow rescheduling the task without cancelling it separately via the `on` command.
        if mod.id in self._role_scheduler:
            self._role_scheduler.cancel(mod.id)
        self._role_scheduler.schedule_at(duration, mod.id, self.reapply_role(mod))

        await ctx.send(f"{Emojis.check_mark} Moderators role has been removed until {until_date}.")

    @duty_group.command(name='on')
    @has_any_role(*MODERATION_ROLES)
    async def on_command(self, ctx: Context) -> None:
        """Re-apply the pingable moderators role."""
        mod = ctx.author
        if mod in self.moderators_role.members:
            await ctx.send(":question: You already have the role.")
            return

        await mod.add_roles(self.moderators_role, reason="Off-duty period canceled.")

        await self.off_duty_mods.delete(mod.id)

        # We assume the task exists. Lack of it may indicate a bug.
        self._role_scheduler.cancel(mod.id)

        await ctx.send(f"{Emojis.check_mark} Moderators role has been re-applied.")

    def cog_unload(self) -> None:
        """Cancel role tasks when the cog unloads."""
        log.trace("Cog unload: canceling role tasks.")
        self._role_scheduler.cancel_all()


def setup(bot: Bot) -> None:
    """Load the Duty cog."""
    bot.add_cog(Duty(bot))
