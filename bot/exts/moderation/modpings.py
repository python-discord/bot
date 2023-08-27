import asyncio
import datetime

import arrow
from async_rediscache import RedisCache
from dateutil.parser import isoparse, parse as dateutil_parse
from discord import Member
from discord.ext.commands import Cog, Context, group, has_any_role
from pydis_core.utils.members import get_or_fetch_member
from pydis_core.utils.scheduling import Scheduler

from bot.bot import Bot
from bot.constants import Emojis, Guild, MODERATION_ROLES, Roles
from bot.converters import Expiry
from bot.log import get_logger
from bot.utils.time import TimestampFormats, discord_timestamp

log = get_logger(__name__)

MAXIMUM_WORK_LIMIT = 16


class ModPings(Cog):
    """Commands for a moderator to turn moderator pings on and off."""

    # RedisCache[discord.Member.id, 'Naïve ISO 8601 string']
    # The cache's keys are mods who have pings off.
    # The cache's values are the times when the role should be re-applied to them, stored in ISO format.
    pings_off_mods = RedisCache()

    # RedisCache[discord.Member.id, 'start timestamp|total worktime in seconds']
    # The cache's keys are mod's ID
    # The cache's values are their pings on schedule timestamp and the total seconds (work time) until pings off
    modpings_schedule = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self._role_scheduler = Scheduler("ModPingsOnOff")
        self._modpings_scheduler = Scheduler("ModPingsSchedule")

        self.guild = None
        self.moderators_role = None

    async def cog_load(self) -> None:
        """Schedule both when to reapply role and all mod ping schedules."""
        # await self.reschedule_modpings_schedule()
        await self.reschedule_roles()

    async def reschedule_roles(self) -> None:
        """Reschedule moderators role re-apply times."""
        await self.bot.wait_until_guild_available()
        self.guild = self.bot.get_guild(Guild.id)
        self.moderators_role = self.guild.get_role(Roles.moderators)

        mod_team = self.guild.get_role(Roles.mod_team)
        pings_on = self.moderators_role.members
        pings_off = await self.pings_off_mods.to_dict()

        log.trace("Applying the moderators role to the mod team where necessary.")
        for mod in mod_team.members:
            if mod in pings_on:  # Make sure that on-duty mods aren't in the redis cache.
                if mod.id in pings_off:
                    await self.pings_off_mods.delete(mod.id)
                continue

            # Keep the role off only for those in the redis cache.
            if mod.id not in pings_off:
                await self.reapply_role(mod)
            else:
                expiry = isoparse(pings_off[mod.id])
                self._role_scheduler.schedule_at(expiry, mod.id, self.reapply_role(mod))

        # At this stage every entry in `pings_off` is expected to have a scheduled task, but that might not be the case
        # if the discord.py cache is missing members, or if the ID belongs to a former moderator.
        for mod_id, expiry_iso in pings_off.items():
            if mod_id not in self._role_scheduler:
                mod = await get_or_fetch_member(self.guild, mod_id)
                # Make sure the member is still a moderator and doesn't have the pingable role.
                if mod is None or mod.get_role(Roles.mod_team) is None or mod.get_role(Roles.moderators) is not None:
                    await self.pings_off_mods.delete(mod_id)
                else:
                    self._role_scheduler.schedule_at(isoparse(expiry_iso), mod_id, self.reapply_role(mod))

    async def reschedule_modpings_schedule(self) -> None:
        """Reschedule moderators schedule ping."""
        await self.bot.wait_until_guild_available()
        schedule_cache = await self.modpings_schedule.to_dict()

        log.info("Scheduling modpings schedule for applicable moderators found in cache.")
        for mod_id, schedule in schedule_cache.items():
            start_timestamp, work_time = schedule.split("|")
            start = datetime.datetime.fromtimestamp(float(start_timestamp), tz=datetime.UTC)

            mod = await self.bot.fetch_user(mod_id)
            self._modpings_scheduler.schedule_at(
                start,
                mod_id,
                self.add_role_schedule(mod, work_time, start)
            )

    async def remove_role_schedule(self, mod: Member, work_time: int, schedule_start: datetime.datetime) -> None:
        """Removes the moderator's role to the given moderator."""
        log.trace(f"Removing moderator role from mod with ID {mod.id}")
        await mod.remove_roles(self.moderators_role, reason="Moderator schedule time expired.")

        # Remove the task before scheduling it again
        self._modpings_scheduler.cancel(mod.id)

        # Add the task again
        log.trace(f"Adding mod pings schedule task again for mod with ID {mod.id}")
        schedule_start += datetime.timedelta(days=1)
        self._modpings_scheduler.schedule_at(
            schedule_start,
            mod.id,
            self.add_role_schedule(mod, work_time, schedule_start)
        )

    async def add_role_schedule(self, mod: Member, work_time: int, schedule_start: datetime.datetime) -> None:
        """Adds the moderator's role to the given moderator."""
        # If the moderator has pings off, then skip adding role
        if mod.id in await self.pings_off_mods.to_dict():
            log.trace(f"Skipping adding moderator role to mod with ID {mod.id} - found in pings off cache.")
        else:
            log.trace(f"Applying moderator role to mod with ID {mod.id}")
            await mod.add_roles(self.moderators_role, reason="Moderator scheduled time started!")

        log.trace(f"Sleeping for {work_time} seconds, worktime for mod with ID {mod.id}")
        await asyncio.sleep(work_time)
        await self.remove_role_schedule(mod, work_time, schedule_start)

    async def reapply_role(self, mod: Member) -> None:
        """Reapply the moderator's role to the given moderator."""
        log.trace(f"Re-applying role to mod with ID {mod.id}.")
        await mod.add_roles(self.moderators_role, reason="Pings off period expired.")
        await self.pings_off_mods.delete(mod.id)

    @group(name="modpings", aliases=("modping",), invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def modpings_group(self, ctx: Context) -> None:
        """Allow the removal and re-addition of the pingable moderators role."""
        await ctx.send_help(ctx.command)

    @modpings_group.command(name="off")
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
        """  # noqa: RUF002
        delta = duration - arrow.utcnow()
        if delta > datetime.timedelta(days=30):
            await ctx.send(":x: Cannot remove the role for longer than 30 days.")
            return

        mod = ctx.author

        until_date = duration.replace(microsecond=0).isoformat()  # Looks noisy with microseconds.
        await mod.remove_roles(self.moderators_role, reason=f"Turned pings off until {until_date}.")

        await self.pings_off_mods.set(mod.id, duration.isoformat())

        # Allow rescheduling the task without cancelling it separately via the `on` command.
        if mod.id in self._role_scheduler:
            self._role_scheduler.cancel(mod.id)
        self._role_scheduler.schedule_at(duration, mod.id, self.reapply_role(mod))

        await ctx.send(
            f"{Emojis.check_mark} Moderators role has been removed "
            f"until {discord_timestamp(duration, format=TimestampFormats.DAY_TIME)}."
        )

    @modpings_group.command(name="on")
    @has_any_role(*MODERATION_ROLES)
    async def on_command(self, ctx: Context) -> None:
        """Re-apply the pingable moderators role."""
        mod = ctx.author
        if mod in self.moderators_role.members:
            await ctx.send(":question: You already have the role.")
            return

        await mod.add_roles(self.moderators_role, reason="Pings off period canceled.")

        await self.pings_off_mods.delete(mod.id)

        # We assume the task exists. Lack of it may indicate a bug.
        self._role_scheduler.cancel(mod.id)

        await ctx.send(f"{Emojis.check_mark} Moderators role has been re-applied.")

    @modpings_group.group(
        name="schedule",
        aliases=("s",),
        invoke_without_command=True
    )
    @has_any_role(*MODERATION_ROLES)
    async def schedule_modpings(self, ctx: Context, start: str, end: str) -> None:
        """Schedule modpings role to be added at <start> and removed at <end> everyday at UTC time!"""
        start, end = dateutil_parse(start), dateutil_parse(end)

        if end < start:
            end += datetime.timedelta(days=1)

        if (end - start) > datetime.timedelta(hours=MAXIMUM_WORK_LIMIT):
            await ctx.send(
                f":x: {ctx.author.mention} You can't have the modpings role for"
                f" more than {MAXIMUM_WORK_LIMIT} hours!"
            )
            return

        if start < datetime.datetime.now(datetime.UTC):
            # The datetime has already gone for the day, so make it tomorrow
            # otherwise the scheduler would schedule it immediately
            start += datetime.timedelta(days=1)

        work_time = (end - start).total_seconds()

        await self.modpings_schedule.set(ctx.author.id, f"{start.timestamp()}|{work_time}")

        if ctx.author.id in self._modpings_scheduler:
            self._modpings_scheduler.cancel(ctx.author.id)

        self._modpings_scheduler.schedule_at(
            start,
            ctx.author.id,
            self.add_role_schedule(ctx.author, work_time, start)
        )

        await ctx.send(
            f"{Emojis.ok_hand} {ctx.author.mention} Scheduled mod pings from "
            f"{discord_timestamp(start, TimestampFormats.TIME)} to "
            f"{discord_timestamp(end, TimestampFormats.TIME)}!"
        )

    @schedule_modpings.command(name="delete", aliases=("del", "d"))
    async def modpings_schedule_delete(self, ctx: Context) -> None:
        """Delete your modpings schedule."""
        self._modpings_scheduler.cancel(ctx.author.id)
        await self.modpings_schedule.delete(ctx.author.id)
        await ctx.send(f"{Emojis.ok_hand} {ctx.author.mention} Deleted your modpings schedule!")

    async def cog_unload(self) -> None:
        """Cancel role tasks when the cog unloads."""
        log.trace("Cog unload: cancelling all scheduled tasks.")
        self._role_scheduler.cancel_all()
        self._modpings_scheduler.cancel_all()


async def setup(bot: Bot) -> None:
    """Load the ModPings cog."""
    await bot.add_cog(ModPings(bot))
