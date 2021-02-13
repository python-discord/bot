from __future__ import annotations

import logging
from collections import namedtuple
from datetime import datetime
from enum import Enum
from typing import Union

from async_rediscache import RedisCache
from dateutil.relativedelta import relativedelta
from discord import Colour, Embed, Member
from discord.ext import tasks
from discord.ext.commands import Cog, Context, group, has_any_role

from bot.bot import Bot
from bot.constants import Channels, Colours, Emojis, Event, Icons, MODERATION_ROLES, Roles
from bot.converters import DurationDelta
from bot.exts.moderation.modlog import ModLog
from bot.utils.messages import format_user
from bot.utils.time import humanize_delta, parse_duration_string

log = logging.getLogger(__name__)

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

    ActionInfo = namedtuple('LogInfoDetails', ['icon', 'emoji', 'color', 'template'])

    SERVER_OPEN = ActionInfo(Icons.defcon_unshutdown, Emojis.defcon_unshutdown, Colours.soft_green, "")
    SERVER_SHUTDOWN = ActionInfo(Icons.defcon_shutdown, Emojis.defcon_shutdown, Colours.soft_red, "")
    DURATION_UPDATE = ActionInfo(
        Icons.defcon_update, Emojis.defcon_update, Colour.blurple(), "**Threshold:** {threshold}\n\n"
    )


class Defcon(Cog):
    """Time-sensitive server defense mechanisms."""

    redis_cache = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.channel = None
        self.threshold = relativedelta(days=0)
        self.expiry = None

        self.bot.loop.create_task(self._sync_settings())

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @redis_cache.atomic_transaction
    async def _sync_settings(self) -> None:
        """On cog load, try to synchronize DEFCON settings to the API."""
        log.trace("Waiting for the guild to become available before syncing.")
        await self.bot.wait_until_guild_available()
        self.channel = await self.bot.fetch_channel(Channels.defcon)

        log.trace("Syncing settings.")

        try:
            settings = await self.redis_cache.to_dict()
            self.threshold = parse_duration_string(settings["threshold"])
        except Exception:
            log.exception("Unable to get DEFCON settings!")
            await self.channel.send(f"<@&{Roles.moderators}> **WARNING**: Unable to get DEFCON settings!")

        else:
            self._update_notifier()
            log.info(f"DEFCON synchronized: {humanize_delta(self.threshold)}")

        await self._update_channel_topic()

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """Check newly joining users to see if they meet the account age threshold."""
        if self.threshold > relativedelta(days=0):
            now = datetime.utcnow()

            if now - member.created_at < self.threshold:
                log.info(f"Rejecting user {member}: Account is too new")

                message_sent = False

                try:
                    await member.send(REJECTION_MESSAGE.format(user=member.mention))

                    message_sent = True
                except Exception:  # TODO
                    log.exception(f"Unable to send rejection message to user: {member}")

                await member.kick(reason="DEFCON active, user is too new")
                self.bot.stats.incr("defcon.leaves")

                message = (
                    f"{format_user(member)} was denied entry because their account is too new."
                )

                if not message_sent:
                    message = f"{message}\n\nUnable to send rejection message via DM; they probably have DMs disabled."

                await self.mod_log.send_log_message(
                    Icons.defcon_denied, Colours.soft_red, "Entry denied",
                    message, member.avatar_url_as(static_format="png")
                )

    @group(name='defcon', aliases=('dc',), invoke_without_command=True)
    async def defcon_group(self, ctx: Context) -> None:
        """Check the DEFCON status or run a subcommand."""
        await ctx.send_help(ctx.command)

    @defcon_group.command(aliases=('s',))
    async def status(self, ctx: Context) -> None:
        """Check the current status of DEFCON mode."""
        embed = Embed(
            colour=Colour.blurple(), title="DEFCON Status",
            description=f"**Threshold:** {humanize_delta(self.threshold)}"
        )

        await ctx.send(embed=embed)

    @defcon_group.command(aliases=('t',))
    async def threshold(self, ctx: Context, threshold: Union[DurationDelta, int]) -> None:
        """Set how old an account must be to join the server."""
        if isinstance(threshold, int):
            threshold = relativedelta(days=threshold)
        await self._defcon_action(ctx, threshold=threshold)

    @defcon_group.command()
    async def shutdown(self, ctx: Context) -> None:
        """Shut down the server by setting send permissions of everyone to False."""
        role = ctx.guild.default_role
        permissions = role.permissions

        permissions.update(send_messages=False, add_reactions=False)
        await role.edit(reason="DEFCON shutdown", permissions=permissions)
        await ctx.send(f"{Action.SERVER_SHUTDOWN.value.emoji} Server shut down.")

    @defcon_group.command()
    async def unshutdown(self, ctx: Context) -> None:
        """Open up the server again by setting send permissions of everyone to None."""
        role = ctx.guild.default_role
        permissions = role.permissions

        permissions.update(send_messages=True, add_reactions=True)
        await role.edit(reason="DEFCON unshutdown", permissions=permissions)
        await ctx.send(f"{Action.SERVER_OPEN.value.emoji} Server reopened.")

    async def _update_channel_topic(self) -> None:
        """Update the #defcon channel topic with the current DEFCON status."""
        new_topic = f"{BASE_CHANNEL_TOPIC}\n(Threshold: {humanize_delta(self.threshold)})"

        self.mod_log.ignore(Event.guild_channel_update, Channels.defcon)
        await self.channel.edit(topic=new_topic)

    @redis_cache.atomic_transaction
    async def _defcon_action(self, ctx: Context, threshold: relativedelta) -> None:
        """Providing a structured way to do a defcon action."""
        self.threshold = threshold

        await self.redis_cache.update(
            {
                'threshold': Defcon._stringify_relativedelta(self.threshold),
            }
        )
        self._update_notifier()

        action = Action.DURATION_UPDATE

        await ctx.send(
            f"{action.value.emoji} DEFCON threshold updated; accounts must be "
            f"{humanize_delta(self.threshold)} old to join the server."
        )
        await self._send_defcon_log(action, ctx.author)
        await self._update_channel_topic()

        self._log_threshold_stat(threshold)

    @staticmethod
    def _stringify_relativedelta(delta: relativedelta) -> str:
        """Convert a relativedelta object to a duration string."""
        units = [("years", "y"), ("months", "m"), ("days", "d"), ("hours", "h"), ("minutes", "m"), ("seconds", "s")]
        return "".join(f"{getattr(delta, unit)}{symbol}" for unit, symbol in units if getattr(delta, unit)) or "0s"

    def _log_threshold_stat(self, threshold: relativedelta) -> None:
        """Adds the threshold to the bot stats in days."""
        utcnow = datetime.utcnow()
        threshold_days = (utcnow + threshold - utcnow).total_seconds() / SECONDS_IN_DAY
        self.bot.stats.gauge("defcon.threshold", threshold_days)

    async def _send_defcon_log(self, action: Action, actor: Member) -> None:
        """Send log message for DEFCON action."""
        info = action.value
        log_msg: str = (
            f"**Staffer:** {actor.mention} {actor} (`{actor.id}`)\n"
            f"{info.template.format(threshold=humanize_delta(self.threshold))}"
        )
        status_msg = f"DEFCON {action.name.lower()}"

        await self.mod_log.send_log_message(info.icon, info.color, status_msg, log_msg)

    def _update_notifier(self) -> None:
        """Start or stop the notifier according to the DEFCON status."""
        if self.threshold != relativedelta(days=0) and not self.defcon_notifier.is_running():
            log.info("DEFCON notifier started.")
            self.defcon_notifier.start()

        elif self.threshold == relativedelta(days=0) and self.defcon_notifier.is_running():
            log.info("DEFCON notifier stopped.")
            self.defcon_notifier.cancel()

    @tasks.loop(hours=1)
    async def defcon_notifier(self) -> None:
        """Routinely notify moderators that DEFCON is active."""
        await self.channel.send(f"Defcon is on and is set to {humanize_delta(self.threshold)}.")

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators in the defcon channel to run commands in this cog."""
        return (await has_any_role(*MODERATION_ROLES).predicate(ctx)) and ctx.channel == self.channel

    def cog_unload(self) -> None:
        """Cancel the notifer task when the cog unloads."""
        log.trace("Cog unload: canceling defcon notifier task.")
        self.defcon_notifier.cancel()


def setup(bot: Bot) -> None:
    """Load the Defcon cog."""
    bot.add_cog(Defcon(bot))
