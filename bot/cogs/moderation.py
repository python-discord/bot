import asyncio
import datetime
import logging
from typing import Dict

from aiohttp import ClientError
from discord import Colour, Embed, Guild, Member, Object, User
from discord.ext.commands import Bot, Context, command, group

from bot import constants
from bot.constants import Keys, Roles, URLs
from bot.converters import InfractionSearchQuery
from bot.decorators import with_role
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)

MODERATION_ROLES = Roles.owner, Roles.admin, Roles.moderator


class Moderation:
    """
    Rowboat replacement moderation tools.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}
        self.expiration_tasks: Dict[str, asyncio.Task] = {}
        self._muted_role = Object(constants.Roles.muted)

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

    # region: Permanent infractions

    @with_role(*MODERATION_ROLES)
    @command(name="warn")
    async def warn(self, ctx: Context, user: User, *, reason: str = None):
        """
        Create a warning infraction in the database for a user.
        :param user: accepts user mention, ID, etc.
        :param reason: The reason for the warning.
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
        except ClientError:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        if reason is None:
            result_message = f":ok_hand: warned {user.mention}."
        else:
            result_message = f":ok_hand: warned {user.mention} ({reason})."

        await ctx.send(result_message)

    @with_role(*MODERATION_ROLES)
    @command(name="kick")
    async def kick(self, ctx, user: Member, *, reason: str = None):
        """
        Kicks a user.
        :param user: accepts user mention, ID, etc.
        :param reason: The reason for the kick.
        """

        try:
            response = await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "kick",
                    "reason": reason,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except ClientError:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        await user.kick(reason=reason)

        if reason is None:
            result_message = f":ok_hand: kicked {user.mention}."
        else:
            result_message = f":ok_hand: kicked {user.mention} ({reason})."

        await ctx.send(result_message)

    @with_role(*MODERATION_ROLES)
    @command(name="ban")
    async def ban(self, ctx: Context, user: User, *, reason: str = None):
        """
        Create a permanent ban infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param reason: The reason for the ban.
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
        except ClientError:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        await ctx.guild.ban(user, reason=reason)

        if reason is None:
            result_message = f":ok_hand: permanently banned {user.mention}."
        else:
            result_message = f":ok_hand: permanently banned {user.mention} ({reason})."

        await ctx.send(result_message)

    @with_role(*MODERATION_ROLES)
    @command(name="mute")
    async def mute(self, ctx: Context, user: Member, *, reason: str = None):
        """
        Create a permanent mute infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param reason: The reason for the mute.
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
        except ClientError:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        # add the mute role
        await user.add_roles(self._muted_role, reason=reason)

        if reason is None:
            result_message = f":ok_hand: permanently muted {user.mention}."
        else:
            result_message = f":ok_hand: permanently muted {user.mention} ({reason})."

        await ctx.send(result_message)

    # endregion
    # region: Temporary infractions

    @with_role(*MODERATION_ROLES)
    @command(name="tempmute")
    async def tempmute(self, ctx: Context, user: Member, duration: str, *, reason: str = None):
        """
        Create a temporary mute infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param duration: The duration for the temporary mute infraction
        :param reason: The reason for the temporary mute.
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
        except ClientError:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
            await ctx.send(f":x: There was an error adding the infraction: {response_object['error_message']}")
            return

        await user.add_roles(self._muted_role, reason=reason)

        infraction_object = response_object["infraction"]
        infraction_expiration = infraction_object["expires_at"]

        loop = asyncio.get_event_loop()
        self.schedule_expiration(loop, infraction_object)

        if reason is None:
            result_message = f":ok_hand: muted {user.mention} until {infraction_expiration}."
        else:
            result_message = f":ok_hand: muted {user.mention} until {infraction_expiration} ({reason})."

        await ctx.send(result_message)

    @with_role(*MODERATION_ROLES)
    @command(name="tempban")
    async def tempban(self, ctx, user: User, duration: str, *, reason: str = None):
        """
        Create a temporary ban infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param duration: The duration for the temporary ban infraction
        :param reason: The reason for the temporary ban.
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
        except ClientError:
            log.exception("There was an error adding an infraction.")
            await ctx.send(":x: There was an error adding the infraction.")
            return

        response_object = await response.json()
        if "error_code" in response_object:
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

    # endregion
    # region: Remove infractions (un- commands)

    @with_role(*MODERATION_ROLES)
    @command(name="unmute")
    async def unmute(self, ctx, user: Member):
        """
        Deactivates the active mute infraction for a user.
        :param user: Accepts user mention, ID, etc.
        """

        try:
            # check the current active infraction
            response = await self.bot.http_session.get(
                URLs.site_infractions_user_type_current.format(
                    user_id=user.id,
                    infraction_type="mute"
                ),
                headers=self.headers
            )
            response_object = await response.json()
            if "error_code" in response_object:
                await ctx.send(f":x: There was an error removing the infraction: {response_object['error_message']}")
                return

            infraction_object = response_object["infraction"]
            if infraction_object is None:
                # no active infraction
                await ctx.send(f":x: There is no active mute infraction for user {user.mention}.")
                return

            await self._deactivate_infraction(infraction_object)
            if infraction_object["expires_at"] is not None:
                self.cancel_expiration(infraction_object["id"])

            await ctx.send(f":ok_hand: Un-muted {user.mention}.")
        except Exception:
            log.exception("There was an error removing an infraction.")
            await ctx.send(":x: There was an error removing the infraction.")
            return

    @with_role(*MODERATION_ROLES)
    @command(name="unban")
    async def unban(self, ctx, user: User):
        """
        Deactivates the active ban infraction for a user.
        :param user: Accepts user mention, ID, etc.
        """

        try:
            # check the current active infraction
            response = await self.bot.http_session.get(
                URLs.site_infractions_user_type_current.format(
                    user_id=user.id,
                    infraction_type="ban"
                ),
                headers=self.headers
            )
            response_object = await response.json()
            if "error_code" in response_object:
                await ctx.send(f":x: There was an error removing the infraction: {response_object['error_message']}")
                return

            infraction_object = response_object["infraction"]
            if infraction_object is None:
                # no active infraction
                await ctx.send(f":x: There is no active ban infraction for user {user.mention}.")
                return

            await self._deactivate_infraction(infraction_object)
            if infraction_object["expires_at"] is not None:
                self.cancel_expiration(infraction_object["id"])

            await ctx.send(f":ok_hand: Un-banned {user.mention}.")
        except Exception:
            log.exception("There was an error removing an infraction.")
            await ctx.send(":x: There was an error removing the infraction.")
            return

    # endregion
    # region: Edit infraction commands

    @with_role(*MODERATION_ROLES)
    @group(name='infraction', aliases=('infr',))
    async def infraction_group(self, ctx: Context):
        """Infraction manipulation commands."""

    @with_role(*MODERATION_ROLES)
    @infraction_group.group(name='edit')
    async def infraction_edit_group(self, ctx: Context):
        """Infraction editing commands."""

    @with_role(*MODERATION_ROLES)
    @infraction_edit_group.command(name="duration")
    async def edit_duration(self, ctx, infraction_id: str, duration: str):
        """
        Sets the duration of the given infraction, relative to the time of updating.
        :param infraction_id: the id (UUID) of the infraction
        :param duration: the new duration of the infraction, relative to the time of updating. Use "permanent" to mark
        the infraction as permanent.
        """

        try:
            if duration == "permanent":
                duration = None
            # check the current active infraction
            response = await self.bot.http_session.patch(
                URLs.site_infractions,
                json={
                    "id": infraction_id,
                    "duration": duration
                },
                headers=self.headers
            )
            response_object = await response.json()
            if "error_code" in response_object or response_object.get("success") is False:
                await ctx.send(f":x: There was an error updating the infraction: {response_object['error_message']}")
                return

            infraction_object = response_object["infraction"]
            # Re-schedule
            self.cancel_expiration(infraction_id)
            loop = asyncio.get_event_loop()
            self.schedule_expiration(loop, infraction_object)

            if duration is None:
                await ctx.send(f":ok_hand: Updated infraction: marked as permanent.")
            else:
                await ctx.send(f":ok_hand: Updated infraction: set to expire on {infraction_object['expires_at']}.")

        except Exception:
            log.exception("There was an error updating an infraction.")
            await ctx.send(":x: There was an error updating the infraction.")
            return

    @with_role(*MODERATION_ROLES)
    @infraction_edit_group.command(name="reason")
    async def edit_reason(self, ctx, infraction_id: str, *, reason: str):
        """
        Sets the reason of the given infraction.
        :param infraction_id: the id (UUID) of the infraction
        :param reason: The new reason of the infraction
        """

        try:
            response = await self.bot.http_session.patch(
                URLs.site_infractions,
                json={
                    "id": infraction_id,
                    "reason": reason
                },
                headers=self.headers
            )
            response_object = await response.json()
            if "error_code" in response_object or response_object.get("success") is False:
                await ctx.send(f":x: There was an error updating the infraction: {response_object['error_message']}")
                return

            await ctx.send(f":ok_hand: Updated infraction: set reason to \"{reason}\".")
        except Exception:
            log.exception("There was an error updating an infraction.")
            await ctx.send(":x: There was an error updating the infraction.")
            return

    # endregion
    # region: Search infractions

    @with_role(*MODERATION_ROLES)
    @infraction_group.command(name="search")
    async def search(self, ctx, arg: InfractionSearchQuery):
        """
        Searches for infractions in the database.
        :param arg: Either a user or a reason string. If a string, you can use the Re2 matching syntax.
        """

        if isinstance(arg, User):
            user: User = arg
            # get infractions for this user
            try:
                response = await self.bot.http_session.get(
                    URLs.site_infractions_user.format(
                        user_id=user.id
                    ),
                    headers=self.headers
                )
                infraction_list = await response.json()
            except ClientError:
                log.exception("There was an error fetching infractions.")
                await ctx.send(":x: There was an error fetching infraction.")
                return

            if not infraction_list:
                await ctx.send(f":warning: No infractions found for {user}.")
                return

            embed = Embed(
                title=f"Infractions for {user} ({len(infraction_list)} total)",
                colour=Colour.orange()
            )

        elif isinstance(arg, str):
            # search by reason
            try:
                response = await self.bot.http_session.get(
                    URLs.site_infractions,
                    headers=self.headers,
                    params={"search": arg}
                )
                infraction_list = await response.json()
            except ClientError:
                log.exception("There was an error fetching infractions.")
                await ctx.send(":x: There was an error fetching infraction.")
                return

            if not infraction_list:
                await ctx.send(f":warning: No infractions matching `{arg}`.")
                return

            embed = Embed(
                title=f"Infractions matching `{arg}` ({len(infraction_list)} total)",
                colour=Colour.orange()
            )

        else:
            await ctx.send(":x: Invalid infraction search query.")
            return

        await LinePaginator.paginate(
            lines=(
                self._infraction_to_string(infraction_object, show_user=isinstance(arg, str))
                for infraction_object in infraction_list
            ),
            ctx=ctx,
            embed=embed,
            empty=True,
            max_lines=3,
            max_size=1000
        )

    # endregion
    # region: Utility functions

    def schedule_expiration(self, loop: asyncio.AbstractEventLoop, infraction_object: dict):
        """
        Schedules a task to expire a temporary infraction.
        :param loop: the asyncio event loop
        :param infraction_object: the infraction object to expire at the end of the task
        """

        infraction_id = infraction_object["id"]
        if infraction_id in self.expiration_tasks:
            return

        task: asyncio.Task = asyncio.ensure_future(self._scheduled_expiration(infraction_object), loop=loop)

        # Silently ignore exceptions in a callback (handles the CancelledError nonsense)
        task.add_done_callback(_silent_exception)

        self.expiration_tasks[infraction_id] = task

    def cancel_expiration(self, infraction_id: str):
        """
        Un-schedules a task set to expire a temporary infraction.
        :param infraction_id: the ID of the infraction in question
        """

        task = self.expiration_tasks.get(infraction_id)
        if task is None:
            log.warning(f"Failed to unschedule {infraction_id}: no task found.")
            return
        task.cancel()
        log.debug(f"Unscheduled {infraction_id}.")
        del self.expiration_tasks[infraction_id]

    async def _scheduled_expiration(self, infraction_object):
        """
        A co-routine which marks an infraction as expired after the delay from the time of scheduling
        to the time of expiration. At the time of expiration, the infraction is marked as inactive on the website,
        and the expiration task is cancelled.
        :param infraction_object: the infraction in question
        """

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
        """
        A co-routine which marks an infraction as inactive on the website. This co-routine does not cancel or
        un-schedule an expiration task.
        :param infraction_object: the infraction in question
        """
        guild: Guild = self.bot.get_guild(constants.Guild.id)
        user_id = int(infraction_object["user"]["user_id"])
        infraction_type = infraction_object["type"]

        if infraction_type == "mute":
            member: Member = guild.get_member(user_id)
            if member:
                # remove the mute role
                await member.remove_roles(self._muted_role)
            else:
                log.warning(f"Failed to un-mute user: {user_id} (not found)")
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

    def _infraction_to_string(self, infraction_object, show_user=False):
        actor_id = int(infraction_object["actor"]["user_id"])
        guild: Guild = self.bot.get_guild(constants.Guild.id)
        actor = guild.get_member(actor_id)
        active = infraction_object["active"] is True

        lines = [
            "**===============**" if active else "===============",
            "Status: {0}".format("__**Active**__" if active else "Inactive"),
            "Type: **{0}**".format(infraction_object["type"]),
            "Reason: {0}".format(infraction_object["reason"] or "*None*"),
            "Created: {0}".format(infraction_object["inserted_at"]),
            "Expires: {0}".format(infraction_object["expires_at"] or "*Permanent*"),
            "Actor: {0}".format(actor.mention if actor else actor_id),
            "ID: `{0}`".format(infraction_object["id"]),
            "**===============**" if active else "==============="
        ]

        if show_user:
            user_id = int(infraction_object["user"]["user_id"])
            user = self.bot.get_user(user_id)
            lines.insert(1, "User: {0}".format(user.mention if user else user_id))

        return "\n".join(lines)

    # endregion


RFC1123_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"


def parse_rfc1123(time_str):
    return datetime.datetime.strptime(time_str, RFC1123_FORMAT).replace(tzinfo=datetime.timezone.utc)


def _silent_exception(future):
    try:
        future.exception()
    except Exception as e:
        log.debug(f"_silent_exception silenced the following exception: {e}")


def setup(bot):
    bot.add_cog(Moderation(bot))
    log.info("Cog loaded: Moderation")
