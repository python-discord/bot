import asyncio
import datetime
import logging
from typing import Dict

from discord import Guild, Member, User
from discord.ext.commands import Bot, Context, command

from bot import constants
from bot.constants import Keys, Roles, URLs
from bot.decorators import with_role

log = logging.getLogger(__name__)


class Moderation:
    """
    Rowboat replacement moderation tools.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}
        self.expiration_tasks: Dict[str, asyncio.Task] = {}

    async def on_ready(self):
        # Schedule expiration for previous infractions
        response = await self.bot.http_session.get(
            URLs.site_infractions,
            params={"dangling": "true"},
            headers=self.headers
        )
        infraction_list = await response.json()
        loop = asyncio.get_event_loop()
        for infraction_object in infraction_list:
            if infraction_object["expires_at"] is not None:
                self.schedule_expiration(loop, infraction_object)

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.warn")
    async def warn(self, ctx: Context, user: User, reason: str = None):
        """
        Create a warning infraction in the database for a user.
        :param user: accepts user mention, ID, etc.
        :param reason: the reason for the warning. Wrap in string quotes for multiple words.
        """

        try:
            response = await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "warning",
                    "reason": reason,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except Exception:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            # something went wrong
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        if reason is None:
            result_message = f":ok_hand: warned {user.mention}."
        else:
            result_message = f":ok_hand: warned {user.mention} ({reason})."

        await ctx.send(result_message)

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.ban")
    async def ban(self, ctx: Context, user: User, reason: str = None):
        """
        Create a permanent ban infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param reason: Wrap in quotes to make reason larger than one word.
        """
        try:
            response = await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "ban",
                    "reason": reason,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except Exception:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            # something went wrong
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        guild: Guild = ctx.guild
        await guild.ban(user, reason=reason)

        if reason is None:
            result_message = f":ok_hand: permanently banned {user.mention}."
        else:
            result_message = f":ok_hand: permanently banned {user.mention} ({reason})."

        await ctx.send(result_message)

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.mute")
    async def mute(self, ctx: Context, user: Member, reason: str = None):
        """
        Create a permanent mute infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param reason: Wrap in quotes to make reason larger than one word.
        """
        try:
            response = await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "mute",
                    "reason": reason,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except Exception:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            # something went wrong
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        await user.edit(reason=reason, mute=True)

        if reason is None:
            result_message = f":ok_hand: permanently muted {user.mention}."
        else:
            result_message = f":ok_hand: permanently muted {user.mention} ({reason})."

        await ctx.send(result_message)

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.tempmute")
    async def tempmute(self, ctx: Context, user: Member, duration: str, reason: str = None):
        """
        Create a temporary mute infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param duration: The duration for the temporary mute infraction
        :param reason: Wrap in quotes to make reason larger than one word.
        """
        try:
            response = await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "mute",
                    "reason": reason,
                    "duration": duration,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except Exception:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            # something went wrong
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        await user.edit(reason=reason, mute=True)

        infraction_object = response_object["infraction"]
        infraction_expiration = infraction_object["expires_at"]

        loop = asyncio.get_event_loop()
        self.schedule_expiration(loop, infraction_object)

        if reason is None:
            result_message = f":ok_hand: muted {user.mention} until {infraction_expiration}."
        else:
            result_message = f":ok_hand: muted {user.mention} until {infraction_expiration} ({reason})."

        await ctx.send(result_message)

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.tempban")
    async def tempban(self, ctx, user: User, duration: str, reason: str = None):
        """
        Create a temporary ban infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param duration: The duration for the temporary ban infraction
        :param reason: Wrap in quotes to make reason larger than one word.
        """
        try:
            response = await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "ban",
                    "reason": reason,
                    "duration": duration,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except Exception:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            # something went wrong
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        guild: Guild = ctx.guild
        await guild.ban(user, reason=reason)

        infraction_object = response_object["infraction"]
        infraction_expiration = infraction_object["expires_at"]

        loop = asyncio.get_event_loop()
        self.schedule_expiration(loop, infraction_object)

        if reason is None:
            result_message = f":ok_hand: banned {user.mention} until {infraction_expiration}."
        else:
            result_message = f":ok_hand: banned {user.mention} until {infraction_expiration} ({reason})."

        await ctx.send(result_message)

    def schedule_expiration(self, loop: asyncio.AbstractEventLoop, infraction_object: dict):
        infraction_id = infraction_object["id"]
        if infraction_id in self.expiration_tasks:
            return

        task: asyncio.Task = asyncio.ensure_future(self._scheduled_expiration(infraction_object), loop=loop)
        # Silently ignore exceptions in a callback (handles the CancelledError nonsense)
        task.add_done_callback(lambda future: future.exception())

        self.expiration_tasks[infraction_id] = task

    def cancel_expiration(self, infraction_id: str):
        task = self.expiration_tasks.get(infraction_id)
        if task is None:
            log.warning(f"Failed to unschedule {infraction_id}: no task found.")
            return
        task.cancel()
        log.debug(f"Unscheduled {infraction_id}.")
        del self.expiration_tasks[infraction_id]

    async def _scheduled_expiration(self, infraction_object):
        infraction_id = infraction_object["id"]

        # transform expiration to delay in seconds
        expiration_datetime = parse_rfc1123(infraction_object["expires_at"])
        delay = expiration_datetime - datetime.datetime.now(tz=datetime.timezone.utc)
        delay_seconds = delay.total_seconds()

        if delay_seconds > 1.0:
            log.debug(f"Scheduling expiration for infraction {infraction_id} in {delay_seconds} seconds")
            await asyncio.sleep(delay_seconds)

        log.debug(f"Marking infraction {infraction_id} as inactive (expired).")
        await self._deactivate_infraction(infraction_object)

        self.cancel_expiration(infraction_object["id"])

    async def _deactivate_infraction(self, infraction_object):
        guild: Guild = self.bot.get_guild(constants.Guild.id)
        user_id = infraction_object["user"]["user_id"]
        infraction_type = infraction_object["type"]

        if infraction_type == "mute":
            member: Member = guild.get_member(user_id)
            if member:
                await member.edit(mute=False)
        elif infraction_type == "ban":
            user: User = self.bot.get_user(user_id)
            await guild.unban(user)

        await self.bot.http_session.patch(
            URLs.site_infractions,
            headers=self.headers,
            json={
                "id": infraction_object["id"],
                "active": False
            }
        )


RFC1123_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"


def parse_rfc1123(time_str):
    return datetime.datetime.strptime(time_str, RFC1123_FORMAT).replace(tzinfo=datetime.timezone.utc)


def setup(bot):
    bot.add_cog(Moderation(bot))
    # Here we'll need to call a command I haven't made yet
    # It'll check the expiry queue and automatically set up tasks for
    # temporary bans, mutes, etc.
    log.info("Cog loaded: Moderation")
