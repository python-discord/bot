from datetime import UTC, timedelta

import arrow
import dateutil
from async_rediscache import RedisCache
from dateutil.parser import isoparse, parse as dateutil_parse
from discord import Member
from discord.ext.commands import BadArgument, Cog, Context, group, has_any_role
from pydis_core.utils.members import get_or_fetch_member
from pydis_core.utils.scheduling import Scheduler

from bot.bot import Bot
from bot.constants import Emojis, Guild, MODERATION_ROLES, Roles
from bot.converters import Expiry
from bot.log import get_logger
from bot.utils.time import TimestampFormats, discord_timestamp

log = get_logger(__name__)

MIN_SHIFT_HOURS = 1
MAX_SHIFT_HOURS = 23


class ModPings(Cog):
    """Commands for a moderator to turn moderator pings on and off."""

    # RedisCache[discord.Member.id, 'Naïve ISO 8601 string']
    # The cache's keys are mods who have pings off.
    # The cache's values are the times when the role should be re-applied to them, stored in ISO format.
    pings_off_mods = RedisCache()

    # RedisCache[discord.Member.id, 'start time in HH:MM|shift duration in seconds']
    # The cache's keys are mods' IDs
    # The cache's values are their pings on schedule timestamp and the total seconds (work time) until pings off
    modpings_schedules = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self._role_scheduler = Scheduler("ModPingsOnOff")
        self._shift_scheduler = Scheduler("ModPingsSchedule")

        self.guild = None
        self.moderators_role = None

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await has_any_role(*MODERATION_ROLES).predicate(ctx)

    async def cog_load(self) -> None:
        """Schedule both when to reapply role and all mod ping schedules."""
        await self.bot.wait_until_guild_available()
        self.guild = self.bot.get_guild(Guild.id)
        self.moderators_role = self.guild.get_role(Roles.moderators)

        await self.reschedule_roles()

    async def reschedule_roles(self) -> None:
        """Reschedule moderators role re-apply times."""
        mod_team = self.guild.get_role(Roles.mod_team)
        pings_on = self.moderators_role.members
        pings_off = await self.pings_off_mods.to_dict()

        log.trace("Applying the moderators role to the mod team where necessary.")
        for mod in mod_team.members:
            if mod in pings_on:  # Make sure that on-duty mods aren't in the redis cache.
                if mod.id in pings_off:
                    await self.pings_off_mods.delete(mod.id)
                continue

            await self.handle_moderator_state(mod)  # Add the role now or schedule it.

        # At this stage every entry in `pings_off` is expected to have a scheduled task, but that might not be the case
        # if the discord.py cache is missing members, or if the ID belongs to a former moderator.
        for mod_id, _ in pings_off.items():
            if mod_id not in self._role_scheduler:
                mod = await get_or_fetch_member(self.guild, mod_id)
                # Make sure the member is still a moderator and doesn't have the pingable role.
                if mod is None or mod.get_role(Roles.mod_team) is None or mod.get_role(Roles.moderators) is not None:
                    await self.pings_off_mods.delete(mod_id)
                else:
                    await self.handle_moderator_state(mod)

        # Similarly handle problems with the schedules cache.
        for mod_id, _ in await self.modpings_schedules.items():
            if mod_id not in self._shift_scheduler:
                mod = await get_or_fetch_member(self.guild, mod_id)
                if mod is None or mod.get_role(Roles.mod_team) is None:
                    await self.modpings_schedules.delete(mod_id)
                else:
                    await self.handle_moderator_state(mod)

    async def handle_moderator_state(self, mod: Member) -> None:
        """Add/remove and/or schedule add/remove of the moderators role according to the mod's state in the caches."""
        expiry_iso = await self.pings_off_mods.get(mod.id, None)
        if expiry_iso is not None:  # The moderator has pings off regardless of recurring schedule.
            if mod.id not in self._role_scheduler:
                self._role_scheduler.schedule_at(isoparse(expiry_iso), mod.id, self.end_pings_off_period(mod))
            return  # The recurring schedule will be handled when the pings off period ends.

        schedule_str = await self.modpings_schedules.get(mod.id, None)
        if schedule_str is None:  # No recurring schedule to handle.
            if mod.get_role(self.moderators_role.id) is None:  # The case of having pings off was already handled.
                await mod.add_roles(self.moderators_role, reason="Pings off period expired.")
            return

        start_time, shift_duration = schedule_str.split("|")
        start = dateutil_parse(start_time).replace(tzinfo=UTC)
        end = start + timedelta(seconds=int(shift_duration))
        now = arrow.utcnow()

        # Move the shift's day such that the end time is in the future and is closest.
        if start - timedelta(days=1) < now < end - timedelta(days=1):  # The shift started yesterday and is ongoing.
            start -= timedelta(days=1)
            end -= timedelta(days=1)
        elif now > end:  # Today's shift already ended, next one is tomorrow.
            start += timedelta(days=1)
            end += timedelta(days=1)

        # The calls to `handle_moderator_state` here aren't recursive as the scheduler creates separate tasks.
        # Start/end have to be differentiated in scheduler task ID. The task is removed from the scheduler only after
        # completion. That means that task with ID X can't schedule a task with the same ID X.
        if start < now < end:
            if mod.get_role(self.moderators_role.id) is None:
                await mod.add_roles(self.moderators_role, reason="Mod active hours started.")
            if f"{mod.id}_end" not in self._shift_scheduler:
                self._shift_scheduler.schedule_at(end, f"{mod.id}_end", self.handle_moderator_state(mod))
        else:
            if mod.get_role(self.moderators_role.id) is not None:
                await mod.remove_roles(self.moderators_role, reason="Mod active hours ended.")
            if f"{mod.id}_start" not in self._shift_scheduler:
                self._shift_scheduler.schedule_at(start, f"{mod.id}_start", self.handle_moderator_state(mod))

    async def end_pings_off_period(self, mod: Member) -> None:
        """Reapply the moderators role to the given moderator."""
        log.trace(f"Ending pings off period of mod with ID {mod.id}.")
        await self.pings_off_mods.delete(mod.id)
        await self.handle_moderator_state(mod)

    @group(name="modpings", aliases=("modping",), invoke_without_command=True)
    async def modpings_group(self, ctx: Context) -> None:
        """Allow the removal and re-addition of the pingable moderators role."""
        await ctx.send_help(ctx.command)

    @modpings_group.command(name="off")
    async def off_command(self, ctx: Context, duration: Expiry) -> None:
        """
        Temporarily removes the pingable moderators role for a set amount of time. Overrides recurring schedule.

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
        """  # noqa: RUF002
        delta = duration - arrow.utcnow()
        if delta > timedelta(days=30):
            await ctx.send(":x: Cannot remove the role for longer than 30 days.")
            return

        mod = ctx.author

        until_date = duration.replace(microsecond=0).isoformat()  # Looks noisy with microseconds.
        await mod.remove_roles(self.moderators_role, reason=f"Turned pings off until {until_date}.")

        await self.pings_off_mods.set(mod.id, duration.isoformat())

        # Allow rescheduling the task without cancelling it separately via the `on` command.
        if mod.id in self._role_scheduler:
            self._role_scheduler.cancel(mod.id)
        self._role_scheduler.schedule_at(duration, mod.id, self.end_pings_off_period(mod))

        await ctx.send(
            f"{Emojis.check_mark} Moderators role has been removed "
            f"until {discord_timestamp(duration, format=TimestampFormats.DAY_TIME)}."
        )

    @modpings_group.command(name="on")
    async def on_command(self, ctx: Context) -> None:
        """
        Stops the pings-off period.

        Puts you back on your daily schedule if there is one, or re-applies the pingable moderators role immediately.
        """
        mod = ctx.author
        if not await self.pings_off_mods.contains(mod.id):
            await ctx.send(":question: You're not in a special off period. Maybe you're off schedule?")
            return

        await self.pings_off_mods.delete(mod.id)

        # We assume the task exists. Lack of it may indicate a bug.
        self._role_scheduler.cancel(mod.id)

        await self.handle_moderator_state(mod)

        await ctx.send(f"{Emojis.check_mark} Moderators role has been re-applied.")  # TODO make message more accurate.

    @modpings_group.group(name="schedule", aliases=("s",), invoke_without_command=True)
    async def schedule_modpings(self, ctx: Context, start_time: str, end_time: str, tz: float | None) -> None:
        """
        Schedule pingable role to be added at `start` time and removed at `end` time. Any previous schedule is dropped.

        Start and end times should be specified in a HH:MM format.

        You may specify a time zone offset for convenience. Times are considered in UTC by default.

        The schedule may be temporarily overridden using the on/off commands.
        """
        try:
            start, end = dateutil_parse(start_time).replace(tzinfo=UTC), dateutil_parse(end_time).replace(tzinfo=UTC)
        except dateutil.parser._parser.ParserError as e:
            raise BadArgument(str(e).capitalize())

        if end < start:
            end += timedelta(days=1)

        if (end - start) < timedelta(hours=MIN_SHIFT_HOURS) or (end - start) > timedelta(hours=MAX_SHIFT_HOURS):
            await ctx.reply(
                f":x: Daily pings-on schedule duration must be between {MIN_SHIFT_HOURS} and {MAX_SHIFT_HOURS} hours."
                " If you want to remove your schedule use the `modpings schedule delete` command."
                " If you want to remove pings for an extended period of time use the `modpings off` command."
            )
            return

        shift_duration = int((end - start).total_seconds())

        if tz is not None:
            start -= timedelta(hours=tz)
            end -= timedelta(hours=tz)
            start_time = f"{start.hour}:{start.minute}"
        await self.modpings_schedules.set(ctx.author.id, f"{start_time}|{shift_duration}")

        if f"{ctx.author.id}_start" in self._shift_scheduler:
            self._shift_scheduler.cancel(f"{ctx.author.id}_start")
        if f"{ctx.author.id}_end" in self._shift_scheduler:
            self._shift_scheduler.cancel(f"{ctx.author.id}_end")

        await self.handle_moderator_state(ctx.author)

        await ctx.reply(
            f"{Emojis.ok_hand} Scheduled mod pings to be on every day from "
            f"{discord_timestamp(start, TimestampFormats.TIME)} to "
            f"{discord_timestamp(end, TimestampFormats.TIME)}."
        )

    @schedule_modpings.command(name="delete", aliases=("del", "d"))
    async def modpings_schedule_delete(self, ctx: Context) -> None:
        """Delete your modpings schedule."""
        self._shift_scheduler.cancel(ctx.author.id)
        await self.modpings_schedules.delete(ctx.author.id)
        await self.handle_moderator_state(ctx.author)
        await ctx.reply(f"{Emojis.ok_hand} Deleted your modpings schedule.")

    @modpings_group.command(name="sync")
    async def sync_command(self, ctx: Context) -> None:
        """
        Attempt to re-sync your pingable moderators role with the stored state.

        If there is a reoccurring problem, please report it.
        """
        await self.handle_moderator_state(ctx.author)
        await ctx.reply(f"{Emojis.ok_hand} State re-synced.")

    async def cog_unload(self) -> None:
        """Cancel role tasks when the cog unloads."""
        log.trace("Cog unload: cancelling all scheduled tasks.")
        self._role_scheduler.cancel_all()
        self._shift_scheduler.cancel_all()


async def setup(bot: Bot) -> None:
    """Load the ModPings cog."""
    await bot.add_cog(ModPings(bot))
