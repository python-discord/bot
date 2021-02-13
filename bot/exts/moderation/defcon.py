from __future__ import annotations

import logging
from collections import namedtuple
from datetime import datetime, timedelta
from enum import Enum
from gettext import ngettext

from async_rediscache import RedisCache
from discord import Colour, Embed, Member
from discord.ext import tasks
from discord.ext.commands import Cog, Context, group, has_any_role

from bot.bot import Bot
from bot.constants import Channels, Colours, Emojis, Event, Icons, MODERATION_ROLES, Roles
from bot.exts.moderation.modlog import ModLog
from bot.utils.messages import format_user

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


class Action(Enum):
    """Defcon Action."""

    ActionInfo = namedtuple('LogInfoDetails', ['icon', 'color', 'template'])

    SERVER_OPEN = ActionInfo(Icons.defcon_unshutdown, Colours.soft_green, "")
    SERVER_SHUTDOWN = ActionInfo(Icons.defcon_shutdown, Colours.soft_red, "")
    DURATION_UPDATE = ActionInfo(Icons.defcon_update, Colour.blurple(), "**Days:** {days}\n\n")


class Defcon(Cog):
    """Time-sensitive server defense mechanisms."""

    redis_cache = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.channel = None
        self.days = timedelta(days=0)
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
            self.days = timedelta(days=settings["days"])
        except Exception:
            log.exception("Unable to get DEFCON settings!")
            await self.channel.send(f"<@&{Roles.moderators}> **WARNING**: Unable to get DEFCON settings!")

        else:
            self._update_notifier()
            log.info(f"DEFCON synchronized: {self.days.days} days")

        await self._update_channel_topic()

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """Check newly joining users to see if they meet the account age threshold."""
        if self.days.days > 0:
            now = datetime.utcnow()

            if now - member.created_at < self.days:
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
    @has_any_role(*MODERATION_ROLES)
    async def defcon_group(self, ctx: Context) -> None:
        """Check the DEFCON status or run a subcommand."""
        await ctx.send_help(ctx.command)

    @defcon_group.command(aliases=('s',))
    @has_any_role(*MODERATION_ROLES)
    async def status(self, ctx: Context) -> None:
        """Check the current status of DEFCON mode."""
        embed = Embed(
            colour=Colour.blurple(), title="DEFCON Status",
            description=f"**Days:** {self.days.days}"
        )

        await ctx.send(embed=embed)

    @defcon_group.command(aliases=('d',))
    @has_any_role(*MODERATION_ROLES)
    async def days(self, ctx: Context, days: int) -> None:
        """Set how old an account must be to join the server, in days."""
        await self._defcon_action(ctx, days=days, action=Action.DURATION_UPDATE)

    async def _update_channel_topic(self) -> None:
        """Update the #defcon channel topic with the current DEFCON status."""
        day_str = "days" if self.days.days > 1 else "day"
        new_topic = f"{BASE_CHANNEL_TOPIC}\n(Threshold: {self.days.days} {day_str})"

        self.mod_log.ignore(Event.guild_channel_update, Channels.defcon)
        await self.channel.edit(topic=new_topic)

    @redis_cache.atomic_transaction
    async def _defcon_action(self, ctx: Context, days: int, action: Action) -> None:
        """Providing a structured way to do an defcon action."""
        self.days = timedelta(days=days)

        await self.redis_cache.update(
            {
                'days': self.days.days,
            }
        )
        self._update_notifier()

        await ctx.send(self._build_defcon_msg(action))
        await self._send_defcon_log(action, ctx.author)
        await self._update_channel_topic()

        self.bot.stats.gauge("defcon.threshold", days)

    def _build_defcon_msg(self, action: Action) -> str:
        """Build in-channel response string for DEFCON action."""
        if action is Action.SERVER_OPEN:
            msg = f"{Emojis.defcon_enabled} Server reopened.\n\n"
        elif action is Action.SERVER_SHUTDOWN:
            msg = f"{Emojis.defcon_disabled} Server shut down.\n\n"
        elif action is Action.DURATION_UPDATE:
            msg = (
                f"{Emojis.defcon_update} DEFCON days updated; accounts must be {self.days.days} "
                f"day{ngettext('', 's', self.days.days)} old to join the server.\n\n"
            )

        return msg

    async def _send_defcon_log(self, action: Action, actor: Member) -> None:
        """Send log message for DEFCON action."""
        info = action.value
        log_msg: str = (
            f"**Staffer:** {actor.mention} {actor} (`{actor.id}`)\n"
            f"{info.template.format(days=self.days.days)}"
        )
        status_msg = f"DEFCON {action.name.lower()}"

        await self.mod_log.send_log_message(info.icon, info.color, status_msg, log_msg)

    def _update_notifier(self) -> None:
        """Start or stop the notifier according to the DEFCON status."""
        if self.days.days != 0 and not self.defcon_notifier.is_running():
            log.info("DEFCON notifier started.")
            self.defcon_notifier.start()

        elif self.days.days == 0 and self.defcon_notifier.is_running():
            log.info("DEFCON notifier stopped.")
            self.defcon_notifier.cancel()

    @tasks.loop(hours=1)
    async def defcon_notifier(self) -> None:
        """Routinely notify moderators that DEFCON is active."""
        await self.channel.send(f"Defcon is on and is set to {self.days.days} day{ngettext('', 's', self.days.days)}.")

    def cog_unload(self) -> None:
        """Cancel the notifer task when the cog unloads."""
        log.trace("Cog unload: canceling defcon notifier task.")
        self.defcon_notifier.cancel()


def setup(bot: Bot) -> None:
    """Load the Defcon cog."""
    bot.add_cog(Defcon(bot))
