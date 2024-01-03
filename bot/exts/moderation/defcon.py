import asyncio
import traceback
from collections import namedtuple
from datetime import datetime
from enum import Enum

import arrow
from async_rediscache import RedisCache
from dateutil.relativedelta import relativedelta
from discord import Colour, Embed, Forbidden, Member, TextChannel, User
from discord.ext import tasks
from discord.ext.commands import Cog, Context, group, has_any_role
from pydis_core.utils import scheduling
from pydis_core.utils.scheduling import Scheduler
from redis import RedisError

from bot.bot import Bot
from bot.constants import Channels, Colours, Emojis, Event, Icons, MODERATION_ROLES, Roles
from bot.converters import DurationDelta, Expiry
from bot.exts.moderation.modlog import ModLog
from bot.log import get_logger
from bot.utils import time
from bot.utils.messages import format_user
from bot.utils.modlog import send_log_message

log = get_logger(__name__)

REJECTION_MESSAGE = """
Hi, {user} - Thanks for your interest in our server!

Due to a current (or detected) cyberattack on our community, we've limited access to the server for new accounts. Since
your account is relatively new, we're unable to provide access to the server at this time.

Even so, thanks for joining! We're very excited at the possibility of having you here, and we hope that this situation
will be resolved soon. In the meantime, please feel free to peruse the resources on our site at
<https://pythondiscord.com/>, and have a nice day!
"""

BASE_CHANNEL_TOPIC = "Python Discord Defense Mechanism"

SECONDS_IN_DAY = 86400


class Action(Enum):
    """Defcon Action."""

    ActionInfo = namedtuple("LogInfoDetails", ["icon", "emoji", "color", "template"])

    SERVER_OPEN = ActionInfo(Icons.defcon_unshutdown, Emojis.defcon_unshutdown, Colours.soft_green, "")
    SERVER_SHUTDOWN = ActionInfo(Icons.defcon_shutdown, Emojis.defcon_shutdown, Colours.soft_red, "")
    DURATION_UPDATE = ActionInfo(
        Icons.defcon_update, Emojis.defcon_update, Colour.og_blurple(), "**Threshold:** {threshold}\n\n"
    )


class Defcon(Cog):
    """Time-sensitive server defense mechanisms."""

    # RedisCache[str, str]
    # The cache's keys are "threshold" and "expiry".
    # The caches' values are strings formatted as valid input to the DurationDelta converter, or empty when off.
    defcon_settings = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.channel = None
        self.threshold = relativedelta(days=0)
        self.expiry = None

        self.scheduler = Scheduler(self.__class__.__name__)

        scheduling.create_task(self._sync_settings(), event_loop=self.bot.loop)

    async def get_mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        while not (cog := self.bot.get_cog("ModLog")):
            await asyncio.sleep(1)
        return cog

    @defcon_settings.atomic_transaction
    async def _sync_settings(self) -> None:
        """On cog load, try to synchronize DEFCON settings to the API."""
        log.trace("Waiting for the guild to become available before syncing.")
        await self.bot.wait_until_guild_available()

        self.channel = await self.bot.fetch_channel(Channels.defcon)

        log.trace("Syncing settings.")

        try:
            settings = await self.defcon_settings.to_dict()
            self.threshold = time.parse_duration_string(settings["threshold"]) if settings.get("threshold") else None
            self.expiry = datetime.fromisoformat(settings["expiry"]) if settings.get("expiry") else None
        except RedisError:
            log.exception("Unable to get DEFCON settings!")
            await self.channel.send(
                f"<@&{Roles.moderators}> <@&{Roles.devops}> **WARNING**: Unable to get DEFCON settings!"
                f"\n\n```{traceback.format_exc()}```"
            )

        else:
            if self.expiry:
                self.scheduler.schedule_at(self.expiry, 0, self._remove_threshold())

            self._update_notifier()
            log.info(f"DEFCON synchronized: {time.humanize_delta(self.threshold) if self.threshold else '-'}")

        await self._update_channel_topic()

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """Check newly joining users to see if they meet the account age threshold."""
        if self.threshold:
            now = arrow.utcnow()

            if now - member.created_at < time.relativedelta_to_timedelta(self.threshold):
                log.info(f"Rejecting user {member}: Account is too new")

                message_sent = False

                try:
                    await member.send(REJECTION_MESSAGE.format(user=member.mention))
                    message_sent = True
                except Forbidden:
                    log.debug(f"Cannot send DEFCON rejection DM to {member}: DMs disabled")
                except Exception:
                    # Broadly catch exceptions because DM isn't critical, but it's imperative to kick them.
                    log.exception(f"Error sending DEFCON rejection message to {member}")

                await member.kick(reason="DEFCON active, user is too new")
                self.bot.stats.incr("defcon.leaves")

                message = (
                    f"{format_user(member)} was denied entry because their account is too new."
                )

                if not message_sent:
                    message = f"{message}\n\nUnable to send rejection message via DM; they probably have DMs disabled."

                await send_log_message(
                    self.bot,
                    Icons.defcon_denied,
                    Colours.soft_red,
                    "Entry denied",
                    message,
                    thumbnail=member.display_avatar.url
                )

    @group(name="defcon", aliases=("dc",), invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def defcon_group(self, ctx: Context) -> None:
        """Check the DEFCON status or run a subcommand."""
        await ctx.send_help(ctx.command)

    @defcon_group.command(aliases=("s",))
    @has_any_role(*MODERATION_ROLES)
    async def status(self, ctx: Context) -> None:
        """Check the current status of DEFCON mode."""
        expiry = time.format_relative(self.expiry) if self.expiry else "-"
        embed = Embed(
            colour=Colour.og_blurple(), title="DEFCON Status",
            description=f"""
                **Threshold:** {time.humanize_delta(self.threshold) if self.threshold else "-"}
                **Expires:** {expiry}
                **Verification level:** {ctx.guild.verification_level.name}
                """
        )

        await ctx.send(embed=embed)

    @defcon_group.command(name="threshold", aliases=("t", "d"))
    @has_any_role(*MODERATION_ROLES)
    async def threshold_command(
        self, ctx: Context, threshold: DurationDelta | int, expiry: Expiry | None = None
    ) -> None:
        """
        Set how old an account must be to join the server.

        The threshold is the minimum required account age. Can accept either a duration string or a number of days.
        Set it to 0 to have no threshold.
        The expiry allows to automatically remove the threshold after a designated time. If no expiry is specified,
        the cog will remind to remove the threshold hourly.
        """
        if isinstance(threshold, int):
            threshold = relativedelta(days=threshold)
        await self._update_threshold(ctx.author, ctx.channel, threshold, expiry)

    @defcon_group.command()
    @has_any_role(Roles.admins)
    async def shutdown(self, ctx: Context) -> None:
        """Shut down the server by setting send permissions of everyone to False."""
        role = ctx.guild.default_role
        permissions = role.permissions

        permissions.update(
            send_messages=False,
            add_reactions=False,
            send_messages_in_threads=False,
            connect=False
        )
        await role.edit(reason="DEFCON shutdown", permissions=permissions)
        await ctx.send(f"{Action.SERVER_SHUTDOWN.value.emoji} Server shut down.")

    @defcon_group.command()
    @has_any_role(Roles.admins)
    async def unshutdown(self, ctx: Context) -> None:
        """Open up the server again by setting send permissions of everyone to None."""
        role = ctx.guild.default_role
        permissions = role.permissions

        permissions.update(
            send_messages=True,
            add_reactions=True,
            send_messages_in_threads=True,
            connect=True
        )
        await role.edit(reason="DEFCON unshutdown", permissions=permissions)
        await ctx.send(f"{Action.SERVER_OPEN.value.emoji} Server reopened.")

    async def _update_channel_topic(self) -> None:
        """Update the #defcon channel topic with the current DEFCON status."""
        threshold = time.humanize_delta(self.threshold) if self.threshold else "-"
        new_topic = f"{BASE_CHANNEL_TOPIC}\n(Threshold: {threshold})"

        (await self.get_mod_log()).ignore(Event.guild_channel_update, Channels.defcon)
        scheduling.create_task(self.channel.edit(topic=new_topic))

    @defcon_settings.atomic_transaction
    async def _update_threshold(
        self,
        author: User,
        channel: TextChannel,
        threshold: relativedelta,
        expiry: Expiry | None = None
    ) -> None:
        """Update the new threshold in the cog, cache, defcon channel, and logs, and additionally schedule expiry."""
        self.threshold = threshold
        if threshold == relativedelta(days=0):  # If the threshold is 0, we don't need to schedule anything
            expiry = None
        self.expiry = expiry

        # Either way, we cancel the old task.
        self.scheduler.cancel_all()
        if self.expiry is not None:
            self.scheduler.schedule_at(expiry, 0, self._remove_threshold())

        self._update_notifier()

        # Make sure to handle the critical part of the update before writing to Redis.
        error = ""
        try:
            await self.defcon_settings.update(
                {
                    "threshold": Defcon._stringify_relativedelta(self.threshold) if self.threshold else "",
                    "expiry": expiry.isoformat() if expiry else 0
                }
            )
        except RedisError:
            error = ", but failed to write to cache"

        action = Action.DURATION_UPDATE

        expiry_message = ""
        if expiry:
            formatted_expiry = time.humanize_delta(expiry, max_units=2)
            expiry_message = f" for the next {formatted_expiry}"

        if self.threshold:
            channel_message = (
                f"updated; accounts must be {time.humanize_delta(self.threshold)} "
                f"old to join the server{expiry_message}"
            )
        else:
            channel_message = "removed"

        message = f"{action.value.emoji} DEFCON threshold {channel_message}{error}."
        await self.channel.send(message)

        # If invoked outside of #defcon send to `ctx.channel` too
        if channel != self.channel:
            await channel.send(message)

        await self._send_defcon_log(action, author)
        await self._update_channel_topic()

        self._log_threshold_stat(threshold)

    async def _remove_threshold(self) -> None:
        """Resets the threshold back to 0."""
        await self._update_threshold(self.bot.user, self.channel, relativedelta(days=0))

    @staticmethod
    def _stringify_relativedelta(delta: relativedelta) -> str:
        """Convert a relativedelta object to a duration string."""
        units = [("years", "y"), ("months", "m"), ("days", "d"), ("hours", "h"), ("minutes", "m"), ("seconds", "s")]
        return "".join(f"{getattr(delta, unit)}{symbol}" for unit, symbol in units if getattr(delta, unit)) or "0s"

    def _log_threshold_stat(self, threshold: relativedelta) -> None:
        """Adds the threshold to the bot stats in days."""
        threshold_days = time.relativedelta_to_timedelta(threshold).total_seconds() / SECONDS_IN_DAY
        self.bot.stats.gauge("defcon.threshold", threshold_days)

    async def _send_defcon_log(self, action: Action, actor: User) -> None:
        """Send log message for DEFCON action."""
        info = action.value
        log_msg: str = (
            f"**Staffer:** {actor.mention} {actor} (`{actor.id}`)\n"
            f"{info.template.format(threshold=(time.humanize_delta(self.threshold) if self.threshold else '-'))}"
        )
        status_msg = f"DEFCON {action.name.lower()}"

        await send_log_message(self.bot, info.icon, info.color, status_msg, log_msg)

    def _update_notifier(self) -> None:
        """Start or stop the notifier according to the DEFCON status."""
        if self.threshold and self.expiry is None and not self.defcon_notifier.is_running():
            log.info("DEFCON notifier started.")
            self.defcon_notifier.start()

        elif (not self.threshold or self.expiry is not None) and self.defcon_notifier.is_running():
            log.info("DEFCON notifier stopped.")
            self.defcon_notifier.cancel()

    @tasks.loop(hours=1)
    async def defcon_notifier(self) -> None:
        """Routinely notify moderators that DEFCON is active."""
        await self.channel.send(f"Defcon is on and is set to {time.humanize_delta(self.threshold)}.")

    async def cog_unload(self) -> None:
        """Cancel the notifer and threshold removal tasks when the cog unloads."""
        log.trace("Cog unload: canceling defcon notifier task.")
        self.defcon_notifier.cancel()
        self.scheduler.cancel_all()


async def setup(bot: Bot) -> None:
    """Load the Defcon cog."""
    await bot.add_cog(Defcon(bot))
