import asyncio
import logging
import typing as t
from contextlib import suppress
from datetime import datetime, timedelta

import discord
from async_rediscache import RedisCache
from discord.ext import tasks
from discord.ext.commands import Cog, Context, command, group, has_any_role
from discord.utils import snowflake_time

from bot import constants
from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.decorators import has_no_roles, in_whitelist
from bot.exts.moderation.modlog import ModLog
from bot.utils.checks import InWhitelistCheckFailure, has_no_roles_check
from bot.utils.messages import format_user

log = logging.getLogger(__name__)

# Sent via DMs once user joins the guild
ON_JOIN_MESSAGE = f"""
Welcome to Python Discord!

To show you what kind of community we are, we've created this video:
https://youtu.be/ZH26PuX3re0

As a new user, you have read-only access to a few select channels to give you a taste of what our server is like. \
In order to see the rest of the channels and to send messages, you first have to accept our rules.

Please visit <#{constants.Channels.verification}> to get started. Thank you!
"""

# Sent via DMs once user verifies
VERIFIED_MESSAGE = f"""
Thanks for verifying yourself!

For your records, these are the documents you accepted:

`1)` Our rules, here: <https://pythondiscord.com/pages/rules>
`2)` Our privacy policy, here: <https://pythondiscord.com/pages/privacy> - you can find information on how to have \
your information removed here as well.

Feel free to review them at any point!

Additionally, if you'd like to receive notifications for the announcements \
we post in <#{constants.Channels.announcements}>
from time to time, you can send `!subscribe` to <#{constants.Channels.bot_commands}> at any time \
to assign yourself the **Announcements** role. We'll mention this role every time we make an announcement.

If you'd like to unsubscribe from the announcement notifications, simply send `!unsubscribe` to \
<#{constants.Channels.bot_commands}>.
"""

ALTERNATE_VERIFIED_MESSAGE = f"""
You're now verified!

You can find a copy of our rules for reference at <https://pythondiscord.com/pages/rules>.

Additionally, if you'd like to receive notifications for the announcements \
we post in <#{constants.Channels.announcements}>
from time to time, you can send `!subscribe` to <#{constants.Channels.bot_commands}> at any time \
to assign yourself the **Announcements** role. We'll mention this role every time we make an announcement.

If you'd like to unsubscribe from the announcement notifications, simply send `!unsubscribe` to \
<#{constants.Channels.bot_commands}>.

To introduce you to our community, we've made the following video:
https://youtu.be/ZH26PuX3re0
"""

# Sent via DMs to users kicked for failing to verify
KICKED_MESSAGE = f"""
Hi! You have been automatically kicked from Python Discord as you have failed to accept our rules \
within `{constants.Verification.kicked_after}` days. If this was an accident, please feel free to join us again!

{constants.Guild.invite}
"""

# Sent periodically in the verification channel
REMINDER_MESSAGE = f"""
<@&{constants.Roles.unverified}>

Welcome to Python Discord! Please read the documents mentioned above and type `!accept` to gain permissions \
to send messages in the community!

You will be kicked if you don't verify within `{constants.Verification.kicked_after}` days.
""".strip()

# An async function taking a Member param
Request = t.Callable[[discord.Member], t.Awaitable]


class StopExecution(Exception):
    """Signals that a task should halt immediately & alert admins."""

    def __init__(self, reason: discord.HTTPException) -> None:
        super().__init__()
        self.reason = reason


class Limit(t.NamedTuple):
    """Composition over config for throttling requests."""

    batch_size: int  # Amount of requests after which to pause
    sleep_secs: int  # Sleep this many seconds after each batch


def mention_role(role_id: int) -> discord.AllowedMentions:
    """Construct an allowed mentions instance that allows pinging `role_id`."""
    return discord.AllowedMentions(roles=[discord.Object(role_id)])


def is_verified(member: discord.Member) -> bool:
    """
    Check whether `member` is considered verified.

    Members are considered verified if they have at least 1 role other than
    the default role (@everyone) and the @Unverified role.
    """
    unverified_roles = {
        member.guild.get_role(constants.Roles.unverified),
        member.guild.default_role,
    }
    return len(set(member.roles) - unverified_roles) > 0


async def safe_dm(coro: t.Coroutine) -> None:
    """
    Execute `coro` ignoring disabled DM warnings.

    The 50_0007 error code indicates that the target user does not accept DMs.
    As it turns out, this error code can appear on both 400 and 403 statuses,
    we therefore catch any Discord exception.

    If the request fails on any other error code, the exception propagates,
    and must be handled by the caller.
    """
    try:
        await coro
    except discord.HTTPException as discord_exc:
        log.trace(f"DM dispatch failed on status {discord_exc.status} with code: {discord_exc.code}")
        if discord_exc.code != 50_007:  # If any reason other than disabled DMs
            raise


class Verification(Cog):
    """
    User verification and role management.

    There are two internal tasks in this cog:

    * `update_unverified_members`
        * Unverified members are given the @Unverified role after configured `unverified_after` days
        * Unverified members are kicked after configured `kicked_after` days
    * `ping_unverified`
        * Periodically ping the @Unverified role in the verification channel

    Statistics are collected in the 'verification.' namespace.

    Moderators+ can use the `verification` command group to start or stop both internal
    tasks, if necessary. Settings are persisted in Redis across sessions.

    Additionally, this cog offers the !accept, !subscribe and !unsubscribe commands,
    and keeps the verification channel clean by deleting messages.
    """

    # Persist task settings & last sent `REMINDER_MESSAGE` id
    # RedisCache[
    #   "tasks_running": int (0 or 1),
    #   "last_reminder": int (discord.Message.id),
    # ]
    task_cache = RedisCache()

    def __init__(self, bot: Bot) -> None:
        """Start internal tasks."""
        self.bot = bot
        self.bot.loop.create_task(self._maybe_start_tasks())

        self.pending_members = set()

    def cog_unload(self) -> None:
        """
        Cancel internal tasks.

        This is necessary, as tasks are not automatically cancelled on cog unload.
        """
        self._stop_tasks(gracefully=False)

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    async def _maybe_start_tasks(self) -> None:
        """
        Poll Redis to check whether internal tasks should start.

        Redis must be interfaced with from an async function.
        """
        log.trace("Checking whether background tasks should begin")
        setting: t.Optional[int] = await self.task_cache.get("tasks_running")  # This can be None if never set

        if setting:
            log.trace("Background tasks will be started")
            self.update_unverified_members.start()
            self.ping_unverified.start()

    def _stop_tasks(self, *, gracefully: bool) -> None:
        """
        Stop the update users & ping @Unverified tasks.

        If `gracefully` is True, the tasks will be able to finish their current iteration.
        Otherwise, they are cancelled immediately.
        """
        log.info(f"Stopping internal tasks ({gracefully=})")
        if gracefully:
            self.update_unverified_members.stop()
            self.ping_unverified.stop()
        else:
            self.update_unverified_members.cancel()
            self.ping_unverified.cancel()

    # region: automatically update unverified users

    async def _verify_kick(self, n_members: int) -> bool:
        """
        Determine whether `n_members` is a reasonable amount of members to kick.

        First, `n_members` is checked against the size of the PyDis guild. If `n_members` are
        more than the configured `kick_confirmation_threshold` of the guild, the operation
        must be confirmed by staff in #core-dev. Otherwise, the operation is seen as safe.
        """
        log.debug(f"Checking whether {n_members} members are safe to kick")

        await self.bot.wait_until_guild_available()  # Ensure cache is populated before we grab the guild
        pydis = self.bot.get_guild(constants.Guild.id)

        percentage = n_members / len(pydis.members)
        if percentage < constants.Verification.kick_confirmation_threshold:
            log.debug(f"Kicking {percentage:.2%} of the guild's population is seen as safe")
            return True

        # Since `n_members` is a suspiciously large number, we will ask for confirmation
        log.debug("Amount of users is too large, requesting staff confirmation")

        core_dev_channel = pydis.get_channel(constants.Channels.dev_core)
        core_dev_ping = f"<@&{constants.Roles.core_developers}>"

        confirmation_msg = await core_dev_channel.send(
            f"{core_dev_ping} Verification determined that `{n_members}` members should be kicked as they haven't "
            f"verified in `{constants.Verification.kicked_after}` days. This is `{percentage:.2%}` of the guild's "
            f"population. Proceed?",
            allowed_mentions=mention_role(constants.Roles.core_developers),
        )

        options = (constants.Emojis.incident_actioned, constants.Emojis.incident_unactioned)
        for option in options:
            await confirmation_msg.add_reaction(option)

        core_dev_ids = [member.id for member in pydis.get_role(constants.Roles.core_developers).members]

        def check(reaction: discord.Reaction, user: discord.User) -> bool:
            """Check whether `reaction` is a valid reaction to `confirmation_msg`."""
            return (
                reaction.message.id == confirmation_msg.id  # Reacted to `confirmation_msg`
                and str(reaction.emoji) in options  # With one of `options`
                and user.id in core_dev_ids  # By a core developer
            )

        timeout = 60 * 5  # Seconds, i.e. 5 minutes
        try:
            choice, _ = await self.bot.wait_for("reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            log.debug("Staff prompt not answered, aborting operation")
            return False
        finally:
            with suppress(discord.HTTPException):
                await confirmation_msg.clear_reactions()

        result = str(choice) == constants.Emojis.incident_actioned
        log.debug(f"Received answer: {choice}, result: {result}")

        # Edit the prompt message to reflect the final choice
        if result is True:
            result_msg = f":ok_hand: {core_dev_ping} Request to kick `{n_members}` members was authorized!"
        else:
            result_msg = f":warning: {core_dev_ping} Request to kick `{n_members}` members was denied!"

        with suppress(discord.HTTPException):
            await confirmation_msg.edit(content=result_msg)

        return result

    async def _alert_admins(self, exception: discord.HTTPException) -> None:
        """
        Ping @Admins with information about `exception`.

        This is used when a critical `exception` caused a verification task to abort.
        """
        await self.bot.wait_until_guild_available()
        log.info(f"Sending admin alert regarding exception: {exception}")

        admins_channel = self.bot.get_guild(constants.Guild.id).get_channel(constants.Channels.admins)
        ping = f"<@&{constants.Roles.admins}>"

        await admins_channel.send(
            f"{ping} Aborted updating unverified users due to the following exception:\n"
            f"```{exception}```\n"
            f"Internal tasks will be stopped.",
            allowed_mentions=mention_role(constants.Roles.admins),
        )

    async def _send_requests(self, members: t.Collection[discord.Member], request: Request, limit: Limit) -> int:
        """
        Pass `members` one by one to `request` handling Discord exceptions.

        This coroutine serves as a generic `request` executor for kicking members and adding
        roles, as it allows us to define the error handling logic in one place only.

        Any `request` has the ability to completely abort the execution by raising `StopExecution`.
        In such a case, the @Admins will be alerted of the reason attribute.

        To avoid rate-limits, pass a `limit` configuring the batch size and the amount of seconds
        to sleep between batches.

        Returns the amount of successful requests. Failed requests are logged at info level.
        """
        log.trace(f"Sending {len(members)} requests")
        n_success, bad_statuses = 0, set()

        for progress, member in enumerate(members, start=1):
            if is_verified(member):  # Member could have verified in the meantime
                continue
            try:
                await request(member)
            except StopExecution as stop_execution:
                await self._alert_admins(stop_execution.reason)
                await self.task_cache.set("tasks_running", 0)
                self._stop_tasks(gracefully=True)  # Gracefully finish current iteration, then stop
                break
            except discord.HTTPException as http_exc:
                bad_statuses.add(http_exc.status)
            else:
                n_success += 1

            if progress % limit.batch_size == 0:
                log.trace(f"Processed {progress} requests, pausing for {limit.sleep_secs} seconds")
                await asyncio.sleep(limit.sleep_secs)

        if bad_statuses:
            log.info(f"Failed to send {len(members) - n_success} requests due to following statuses: {bad_statuses}")

        return n_success

    async def _add_kick_note(self, member: discord.Member) -> None:
        """
        Post a note regarding `member` being kicked to site.

        Allows keeping track of kicked members for auditing purposes.
        """
        payload = {
            "active": False,
            "actor": self.bot.user.id,  # Bot actions this autonomously
            "expires_at": None,
            "hidden": True,
            "reason": "Verification kick",
            "type": "note",
            "user": member.id,
        }

        log.trace(f"Posting kick note for member {member} ({member.id})")
        try:
            await self.bot.api_client.post("bot/infractions", json=payload)
        except ResponseCodeError as api_exc:
            log.warning("Failed to post kick note", exc_info=api_exc)

    async def _kick_members(self, members: t.Collection[discord.Member]) -> int:
        """
        Kick `members` from the PyDis guild.

        Due to strict ratelimits on sending messages (120 requests / 60 secs), we sleep for a second
        after each 2 requests to allow breathing room for other features.

        Note that this is a potentially destructive operation. Returns the amount of successful requests.
        """
        log.info(f"Kicking {len(members)} members (not verified after {constants.Verification.kicked_after} days)")

        async def kick_request(member: discord.Member) -> None:
            """Send `KICKED_MESSAGE` to `member` and kick them from the guild."""
            try:
                await safe_dm(member.send(KICKED_MESSAGE))  # Suppress disabled DMs
            except discord.HTTPException as suspicious_exception:
                raise StopExecution(reason=suspicious_exception)
            await member.kick(reason=f"User has not verified in {constants.Verification.kicked_after} days")
            await self._add_kick_note(member)

        n_kicked = await self._send_requests(members, kick_request, Limit(batch_size=2, sleep_secs=1))
        self.bot.stats.incr("verification.kicked", count=n_kicked)

        return n_kicked

    async def _give_role(self, members: t.Collection[discord.Member], role: discord.Role) -> int:
        """
        Give `role` to all `members`.

        We pause for a second after batches of 25 requests to ensure ratelimits aren't exceeded.

        Returns the amount of successful requests.
        """
        log.info(
            f"Assigning {role} role to {len(members)} members (not verified "
            f"after {constants.Verification.unverified_after} days)"
        )

        async def role_request(member: discord.Member) -> None:
            """Add `role` to `member`."""
            await member.add_roles(role, reason=f"Not verified after {constants.Verification.unverified_after} days")

        return await self._send_requests(members, role_request, Limit(batch_size=25, sleep_secs=1))

    async def _check_members(self) -> t.Tuple[t.Set[discord.Member], t.Set[discord.Member]]:
        """
        Check in on the verification status of PyDis members.

        This coroutine finds two sets of users:
        * Not verified after configured `unverified_after` days, should be given the @Unverified role
        * Not verified after configured `kicked_after` days, should be kicked from the guild

        These sets are always disjoint, i.e. share no common members.
        """
        await self.bot.wait_until_guild_available()  # Ensure cache is ready
        pydis = self.bot.get_guild(constants.Guild.id)

        unverified = pydis.get_role(constants.Roles.unverified)
        current_dt = datetime.utcnow()  # Discord timestamps are UTC

        # Users to be given the @Unverified role, and those to be kicked, these should be entirely disjoint
        for_role, for_kick = set(), set()

        log.debug("Checking verification status of guild members")
        for member in pydis.members:

            # Skip verified members, bots, and members for which we do not know their join date,
            # this should be extremely rare but docs mention that it can happen
            if is_verified(member) or member.bot or member.joined_at is None:
                continue

            # At this point, we know that `member` is an unverified user, and we will decide what
            # to do with them based on time passed since their join date
            since_join = current_dt - member.joined_at

            if since_join > timedelta(days=constants.Verification.kicked_after):
                for_kick.add(member)  # User should be removed from the guild

            elif (
                since_join > timedelta(days=constants.Verification.unverified_after)
                and unverified not in member.roles
            ):
                for_role.add(member)  # User should be given the @Unverified role

        log.debug(f"Found {len(for_role)} users for {unverified} role, {len(for_kick)} users to be kicked")
        return for_role, for_kick

    @tasks.loop(minutes=30)
    async def update_unverified_members(self) -> None:
        """
        Periodically call `_check_members` and update unverified members accordingly.

        After each run, a summary will be sent to the modlog channel. If a suspiciously high
        amount of members to be kicked is found, the operation is guarded by `_verify_kick`.
        """
        log.info("Updating unverified guild members")

        await self.bot.wait_until_guild_available()
        unverified = self.bot.get_guild(constants.Guild.id).get_role(constants.Roles.unverified)

        for_role, for_kick = await self._check_members()

        if not for_role:
            role_report = f"Found no users to be assigned the {unverified.mention} role."
        else:
            n_roles = await self._give_role(for_role, unverified)
            role_report = f"Assigned {unverified.mention} role to `{n_roles}`/`{len(for_role)}` members."

        if not for_kick:
            kick_report = "Found no users to be kicked."
        elif not await self._verify_kick(len(for_kick)):
            kick_report = f"Not authorized to kick `{len(for_kick)}` members."
        else:
            n_kicks = await self._kick_members(for_kick)
            kick_report = f"Kicked `{n_kicks}`/`{len(for_kick)}` members from the guild."

        await self.mod_log.send_log_message(
            icon_url=self.bot.user.avatar_url,
            colour=discord.Colour.blurple(),
            title="Verification system",
            text=f"{kick_report}\n{role_report}",
        )

    # endregion
    # region: periodically ping @Unverified

    @tasks.loop(hours=constants.Verification.reminder_frequency)
    async def ping_unverified(self) -> None:
        """
        Delete latest `REMINDER_MESSAGE` and send it again.

        This utilizes RedisCache to persist the latest reminder message id.
        """
        await self.bot.wait_until_guild_available()
        verification = self.bot.get_guild(constants.Guild.id).get_channel(constants.Channels.verification)

        last_reminder: t.Optional[int] = await self.task_cache.get("last_reminder")

        if last_reminder is not None:
            log.trace(f"Found verification reminder message in cache, deleting: {last_reminder}")

            with suppress(discord.HTTPException):  # If something goes wrong, just ignore it
                await self.bot.http.delete_message(verification.id, last_reminder)

        log.trace("Sending verification reminder")
        new_reminder = await verification.send(
            REMINDER_MESSAGE, allowed_mentions=mention_role(constants.Roles.unverified),
        )

        await self.task_cache.set("last_reminder", new_reminder.id)

    @ping_unverified.before_loop
    async def _before_first_ping(self) -> None:
        """
        Sleep until `REMINDER_MESSAGE` should be sent again.

        If latest reminder is not cached, exit instantly. Otherwise, wait wait until the
        configured `reminder_frequency` has passed.
        """
        last_reminder: t.Optional[int] = await self.task_cache.get("last_reminder")

        if last_reminder is None:
            log.trace("Latest verification reminder message not cached, task will not wait")
            return

        # Convert cached message id into a timestamp
        time_since = datetime.utcnow() - snowflake_time(last_reminder)
        log.trace(f"Time since latest verification reminder: {time_since}")

        to_sleep = timedelta(hours=constants.Verification.reminder_frequency) - time_since
        log.trace(f"Time to sleep until next ping: {to_sleep}")

        # Delta can be negative if `reminder_frequency` has already passed
        secs = max(to_sleep.total_seconds(), 0)
        await asyncio.sleep(secs)

    # endregion
    # region: listeners

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Attempt to send initial direct message to each new member."""
        if member.guild.id != constants.Guild.id:
            return  # Only listen for PyDis events

        raw_member = await self.bot.http.get_member(member.guild.id, member.id)

        # If the user has the pending flag set, they will be using the alternate
        # gate and will not need a welcome DM with verification instructions.
        # We will send them an alternate DM once they verify with the welcome
        # video when they pass the gate.
        if raw_member.get("pending"):
            return

        log.trace(f"Sending on join message to new member: {member.id}")
        try:
            await safe_dm(member.send(ON_JOIN_MESSAGE))
        except discord.HTTPException:
            log.exception("DM dispatch failed on unexpected error code")

    @Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Check if we need to send a verification DM to a gated user."""
        if before.pending is True and after.pending is False:
            try:
                # If the member has not received a DM from our !accept command
                # and has gone through the alternate gating system we should send
                # our alternate welcome DM which includes info such as our welcome
                # video.
                await safe_dm(after.send(ALTERNATE_VERIFIED_MESSAGE))
            except discord.HTTPException:
                log.exception("DM dispatch failed on unexpected error code")

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Check new message event for messages to the checkpoint channel & process."""
        if message.channel.id != constants.Channels.verification:
            return  # Only listen for #checkpoint messages

        if message.content == REMINDER_MESSAGE:
            return  # Ignore bots own verification reminder

        if message.author.bot:
            # They're a bot, delete their message after the delay.
            await message.delete(delay=constants.Verification.bot_message_delete_delay)
            return

        # if a user mentions a role or guild member
        # alert the mods in mod-alerts channel
        if message.mentions or message.role_mentions:
            log.debug(
                f"{message.author} mentioned one or more users "
                f"and/or roles in {message.channel.name}"
            )

            embed_text = (
                f"{format_user(message.author)} sent a message in "
                f"{message.channel.mention} that contained user and/or role mentions."
                f"\n\n**Original message:**\n>>> {message.content}"
            )

            # Send pretty mod log embed to mod-alerts
            await self.mod_log.send_log_message(
                icon_url=constants.Icons.filtering,
                colour=discord.Colour(constants.Colours.soft_red),
                title=f"User/Role mentioned in {message.channel.name}",
                text=embed_text,
                thumbnail=message.author.avatar_url_as(static_format="png"),
                channel_id=constants.Channels.mod_alerts,
            )

        ctx: Context = await self.bot.get_context(message)
        if ctx.command is not None and ctx.command.name == "accept":
            return

        if any(r.id == constants.Roles.verified for r in ctx.author.roles):
            log.info(
                f"{ctx.author} posted '{ctx.message.content}' "
                "in the verification channel, but is already verified."
            )
            return

        log.debug(
            f"{ctx.author} posted '{ctx.message.content}' in the verification "
            "channel. We are providing instructions how to verify."
        )
        await ctx.send(
            f"{ctx.author.mention} Please type `!accept` to verify that you accept our rules, "
            f"and gain access to the rest of the server.",
            delete_after=20
        )

        log.trace(f"Deleting the message posted by {ctx.author}")
        with suppress(discord.NotFound):
            await ctx.message.delete()

    # endregion
    # region: task management commands

    @has_any_role(*constants.MODERATION_ROLES)
    @group(name="verification")
    async def verification_group(self, ctx: Context) -> None:
        """Manage internal verification tasks."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @verification_group.command(name="status")
    async def status_cmd(self, ctx: Context) -> None:
        """Check whether verification tasks are running."""
        log.trace("Checking status of verification tasks")

        if self.update_unverified_members.is_running():
            update_status = f"{constants.Emojis.incident_actioned} Member update task is running."
        else:
            update_status = f"{constants.Emojis.incident_unactioned} Member update task is **not** running."

        mention = f"<@&{constants.Roles.unverified}>"
        if self.ping_unverified.is_running():
            ping_status = f"{constants.Emojis.incident_actioned} Ping {mention} task is running."
        else:
            ping_status = f"{constants.Emojis.incident_unactioned} Ping {mention} task is **not** running."

        embed = discord.Embed(
            title="Verification system",
            description=f"{update_status}\n{ping_status}",
            colour=discord.Colour.blurple(),
        )
        await ctx.send(embed=embed)

    @verification_group.command(name="start")
    async def start_cmd(self, ctx: Context) -> None:
        """Start verification tasks if they are not already running."""
        log.info("Starting verification tasks")

        if not self.update_unverified_members.is_running():
            self.update_unverified_members.start()

        if not self.ping_unverified.is_running():
            self.ping_unverified.start()

        await self.task_cache.set("tasks_running", 1)

        colour = discord.Colour.blurple()
        await ctx.send(embed=discord.Embed(title="Verification system", description="Done. :ok_hand:", colour=colour))

    @verification_group.command(name="stop", aliases=["kill"])
    async def stop_cmd(self, ctx: Context) -> None:
        """Stop verification tasks."""
        log.info("Stopping verification tasks")

        self._stop_tasks(gracefully=False)
        await self.task_cache.set("tasks_running", 0)

        colour = discord.Colour.blurple()
        await ctx.send(embed=discord.Embed(title="Verification system", description="Tasks canceled.", colour=colour))

    # endregion
    # region: accept and subscribe commands

    def _bump_verified_stats(self, verified_member: discord.Member) -> None:
        """
        Increment verification stats for `verified_member`.

        Each member falls into one of the three categories:
            * Verified within 24 hours after joining
            * Does not have @Unverified role yet
            * Does have @Unverified role

        Stats for member kicking are handled separately.
        """
        if verified_member.joined_at is None:  # Docs mention this can happen
            return

        if (datetime.utcnow() - verified_member.joined_at) < timedelta(hours=24):
            category = "accepted_on_day_one"
        elif constants.Roles.unverified not in [role.id for role in verified_member.roles]:
            category = "accepted_before_unverified"
        else:
            category = "accepted_after_unverified"

        log.trace(f"Bumping verification stats in category: {category}")
        self.bot.stats.incr(f"verification.{category}")

    @command(name='accept', aliases=('verified', 'accepted'), hidden=True)
    @has_no_roles(constants.Roles.verified)
    @in_whitelist(channels=(constants.Channels.verification,))
    async def accept_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Accept our rules and gain access to the rest of the server."""
        log.debug(f"{ctx.author} called !accept. Assigning the 'Developer' role.")
        await ctx.author.add_roles(discord.Object(constants.Roles.verified), reason="Accepted the rules")

        self._bump_verified_stats(ctx.author)  # This checks for @Unverified so make sure it's not yet removed

        if constants.Roles.unverified in [role.id for role in ctx.author.roles]:
            log.debug(f"Removing Unverified role from: {ctx.author}")
            await ctx.author.remove_roles(discord.Object(constants.Roles.unverified))

        try:
            await safe_dm(ctx.author.send(VERIFIED_MESSAGE))
        except discord.HTTPException:
            log.exception(f"Sending welcome message failed for {ctx.author}.")
        finally:
            log.trace(f"Deleting accept message by {ctx.author}.")
            with suppress(discord.NotFound):
                self.mod_log.ignore(constants.Event.message_delete, ctx.message.id)
                await ctx.message.delete()

    @command(name='subscribe')
    @in_whitelist(channels=(constants.Channels.bot_commands,))
    async def subscribe_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Subscribe to announcement notifications by assigning yourself the role."""
        has_role = False

        for role in ctx.author.roles:
            if role.id == constants.Roles.announcements:
                has_role = True
                break

        if has_role:
            await ctx.send(f"{ctx.author.mention} You're already subscribed!")
            return

        log.debug(f"{ctx.author} called !subscribe. Assigning the 'Announcements' role.")
        await ctx.author.add_roles(discord.Object(constants.Roles.announcements), reason="Subscribed to announcements")

        log.trace(f"Deleting the message posted by {ctx.author}.")

        await ctx.send(
            f"{ctx.author.mention} Subscribed to <#{constants.Channels.announcements}> notifications.",
        )

    @command(name='unsubscribe')
    @in_whitelist(channels=(constants.Channels.bot_commands,))
    async def unsubscribe_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Unsubscribe from announcement notifications by removing the role from yourself."""
        has_role = False

        for role in ctx.author.roles:
            if role.id == constants.Roles.announcements:
                has_role = True
                break

        if not has_role:
            await ctx.send(f"{ctx.author.mention} You're already unsubscribed!")
            return

        log.debug(f"{ctx.author} called !unsubscribe. Removing the 'Announcements' role.")
        await ctx.author.remove_roles(
            discord.Object(constants.Roles.announcements), reason="Unsubscribed from announcements"
        )

        log.trace(f"Deleting the message posted by {ctx.author}.")

        await ctx.send(
            f"{ctx.author.mention} Unsubscribed from <#{constants.Channels.announcements}> notifications."
        )

    # endregion
    # region: miscellaneous

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Check for & ignore any InWhitelistCheckFailure."""
        if isinstance(error, InWhitelistCheckFailure):
            error.handled = True

    @staticmethod
    async def bot_check(ctx: Context) -> bool:
        """Block any command within the verification channel that is not !accept."""
        is_verification = ctx.channel.id == constants.Channels.verification
        if is_verification and await has_no_roles_check(ctx, *constants.MODERATION_ROLES):
            return ctx.command.name == "accept"
        else:
            return True

    @command(name='verify')
    @has_any_role(*constants.MODERATION_ROLES)
    async def apply_developer_role(self, ctx: Context, user: discord.Member) -> None:
        """Command for moderators to apply the Developer role to any user."""
        log.trace(f'verify command called by {ctx.author} for {user.id}.')
        developer_role = self.bot.get_guild(constants.Guild.id).get_role(constants.Roles.verified)

        if developer_role in user.roles:
            log.trace(f'{user.id} is already a developer, aborting.')
            await ctx.send(f'{constants.Emojis.cross_mark} {user.mention} is already a developer.')
            return

        await user.add_roles(developer_role)
        await safe_dm(user.send(ALTERNATE_VERIFIED_MESSAGE))
        log.trace(f'Developer role successfully applied to {user.id}')
        await ctx.send(f'{constants.Emojis.check_mark} Developer role applied to {user.mention}.')

    # endregion


def setup(bot: Bot) -> None:
    """Load the Verification cog."""
    bot.add_cog(Verification(bot))
