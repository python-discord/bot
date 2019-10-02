import logging
import textwrap
import typing as t

import dateutil.parser
import discord
from discord import Member
from discord.ext import commands
from discord.ext.commands import Context, command

from bot import constants
from bot.api import ResponseCodeError
from bot.constants import Colours, Event
from bot.converters import Duration
from bot.decorators import respect_role_hierarchy
from bot.utils import time
from bot.utils.checks import with_role_check
from bot.utils.scheduling import Scheduler
from . import utils
from .modlog import ModLog
from .utils import MemberObject

log = logging.getLogger(__name__)

MemberConverter = t.Union[utils.UserTypes, utils.proxy_user]


class Infractions(Scheduler, commands.Cog):
    """Server moderation tools."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._muted_role = discord.Object(constants.Roles.muted)
        super().__init__()

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Schedule expiration for previous infractions."""
        infractions = await self.bot.api_client.get(
            'bot/infractions',
            params={'active': 'true'}
        )
        for infraction in infractions:
            if infraction["expires_at"] is not None:
                self.schedule_task(self.bot.loop, infraction["id"], infraction)

    # region: Permanent infractions

    @command()
    async def warn(self, ctx: Context, user: MemberConverter, *, reason: str = None) -> None:
        """Warn a user for the given reason."""
        infraction = await utils.post_infraction(ctx, user, reason, "warning")
        if infraction is None:
            return

        await self.apply_infraction(ctx, infraction, user)

    @command()
    async def kick(self, ctx: Context, user: Member, *, reason: str = None) -> None:
        """Kick a user for the given reason."""
        await self.apply_kick(ctx, user, reason)

    @command()
    async def ban(self, ctx: Context, user: MemberConverter, *, reason: str = None) -> None:
        """Permanently ban a user for the given reason."""
        await self.apply_ban(ctx, user, reason)

    # endregion
    # region: Temporary infractions

    @command(aliases=('mute',))
    async def tempmute(self, ctx: Context, user: Member, duration: Duration, *, reason: str = None) -> None:
        """
        Temporarily mute a user for the given reason and duration.

        A unit of time should be appended to the duration:
        y (years), m (months), w (weeks), d (days), h (hours), M (minutes), s (seconds)
        """
        await self.apply_mute(ctx, user, reason, expires_at=duration)

    @command()
    async def tempban(self, ctx: Context, user: MemberConverter, duration: Duration, *, reason: str = None) -> None:
        """
        Temporarily ban a user for the given reason and duration.

        A unit of time should be appended to the duration:
        y (years), m (months), w (weeks), d (days), h (hours), M (minutes), s (seconds)
        """
        await self.apply_ban(ctx, user, reason, expires_at=duration)

    # endregion
    # region: Permanent shadow infractions

    @command(hidden=True)
    async def note(self, ctx: Context, user: MemberConverter, *, reason: str = None) -> None:
        """Create a private note for a user with the given reason without notifying the user."""
        infraction = await utils.post_infraction(ctx, user, reason, "note", hidden=True)
        if infraction is None:
            return

        await self.apply_infraction(ctx, infraction, user)

    @command(hidden=True, aliases=['shadowkick', 'skick'])
    async def shadow_kick(self, ctx: Context, user: Member, *, reason: str = None) -> None:
        """Kick a user for the given reason without notifying the user."""
        await self.apply_kick(ctx, user, reason, hidden=True)

    @command(hidden=True, aliases=['shadowban', 'sban'])
    async def shadow_ban(self, ctx: Context, user: MemberConverter, *, reason: str = None) -> None:
        """Permanently ban a user for the given reason without notifying the user."""
        await self.apply_ban(ctx, user, reason, hidden=True)

    # endregion
    # region: Temporary shadow infractions

    @command(hidden=True, aliases=["shadowtempmute, stempmute", "shadowmute", "smute"])
    async def shadow_tempmute(
        self, ctx: Context, user: Member, duration: Duration, *, reason: str = None
    ) -> None:
        """
        Temporarily mute a user for the given reason and duration without notifying the user.

        A unit of time should be appended to the duration:
        y (years), m (months), w (weeks), d (days), h (hours), M (minutes), s (seconds)
        """
        await self.apply_mute(ctx, user, reason, expires_at=duration, hidden=True)

    @command(hidden=True, aliases=["shadowtempban, stempban"])
    async def shadow_tempban(
        self, ctx: Context, user: MemberConverter, duration: Duration, *, reason: str = None
    ) -> None:
        """
        Temporarily ban a user for the given reason and duration without notifying the user.

        A unit of time should be appended to the duration:
        y (years), m (months), w (weeks), d (days), h (hours), M (minutes), s (seconds)
        """
        await self.apply_ban(ctx, user, reason, expires_at=duration, hidden=True)

    # endregion
    # region: Remove infractions (un- commands)

    @command()
    async def unmute(self, ctx: Context, user: MemberConverter) -> None:
        """Prematurely end the active mute infraction for the user."""
        await self.pardon_infraction(ctx, "mute", user)

    @command()
    async def unban(self, ctx: Context, user: MemberConverter) -> None:
        """Prematurely end the active ban infraction for the user."""
        await self.pardon_infraction(ctx, "ban", user)

    # endregion
    # region: Base infraction functions

    async def apply_mute(self, ctx: Context, user: Member, reason: str, **kwargs) -> None:
        """Apply a mute infraction with kwargs passed to `post_infraction`."""
        if await utils.already_has_active_infraction(ctx, user, "mute"):
            return

        infraction = await utils.post_infraction(ctx, user, "mute", reason, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_update, user.id)

        action = user.add_roles(self._muted_role, reason=reason)
        await self.apply_infraction(ctx, infraction, user, action)

    @respect_role_hierarchy()
    async def apply_kick(self, ctx: Context, user: Member, reason: str, **kwargs) -> None:
        """Apply a kick infraction with kwargs passed to `post_infraction`."""
        infraction = await utils.post_infraction(ctx, user, "kick", reason, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_remove, user.id)

        action = user.kick(reason=reason)
        await self.apply_infraction(ctx, infraction, user, action)

    @respect_role_hierarchy()
    async def apply_ban(self, ctx: Context, user: MemberObject, reason: str, **kwargs) -> None:
        """Apply a ban infraction with kwargs passed to `post_infraction`."""
        if await utils.already_has_active_infraction(ctx, user, "ban"):
            return

        infraction = await utils.post_infraction(ctx, user, "ban", reason, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_ban, user.id)
        self.mod_log.ignore(Event.member_remove, user.id)

        action = ctx.guild.ban(user, reason=reason, delete_message_days=0)
        await self.apply_infraction(ctx, infraction, user, action)

    # endregion
    # region: Utility functions

    async def _scheduled_task(self, infraction: utils.Infraction) -> None:
        """
        Marks an infraction expired after the delay from time of scheduling to time of expiration.

        At the time of expiration, the infraction is marked as inactive on the website and the
        expiration task is cancelled.
        """
        _id = infraction["id"]

        expiry = dateutil.parser.isoparse(infraction["expires_at"]).replace(tzinfo=None)
        await time.wait_until(expiry)

        log.debug(f"Marking infraction {_id} as inactive (expired).")
        await self.deactivate_infraction(infraction)

    async def deactivate_infraction(
        self,
        infraction: utils.Infraction,
        send_log: bool = True
    ) -> t.Dict[str, str]:
        """
        Deactivate an active infraction and return a dictionary of lines to send in a mod log.

        The infraction is removed from Discord, marked as inactive in the database, and has its
        expiration task cancelled. If `send_log` is True, a mod log is sent for the
        deactivation of the infraction.

        Supported infraction types are mute and ban. Other types will raise a ValueError.
        """
        guild = self.bot.get_guild(constants.Guild.id)
        user_id = infraction["user"]
        _type = infraction["type"]
        _id = infraction["id"]
        reason = f"Infraction #{_id} expired or was pardoned."

        log_text = {
            "Member": str(user_id),
            "Actor": str(self.bot.user)
        }

        try:
            if _type == "mute":
                user = guild.get_member(user_id)
                if user:
                    # Remove the muted role.
                    self.mod_log.ignore(Event.member_update, user.id)
                    await user.remove_roles(self._muted_role, reason=reason)

                    # DM the user about the expiration.
                    notified = await utils.notify_pardon(
                        user=user,
                        title="You have been unmuted.",
                        content="You may now send messages in the server.",
                        icon_url=utils.INFRACTION_ICONS["mute"][1]
                    )

                    log_text["Member"] = f"{user.mention}(`{user.id}`)"
                    log_text["DM"] = "Sent" if notified else "**Failed**"
                else:
                    log.info(f"Failed to unmute user {user_id}: user not found")
                    log_text["Failure"] = "User was not found in the guild."
            elif _type == "ban":
                user = discord.Object(user_id)
                self.mod_log.ignore(Event.member_unban, user_id)
                try:
                    await guild.unban(user, reason=reason)
                except discord.NotFound:
                    log.info(f"Failed to unban user {user_id}: no active ban found on Discord")
                    log_text["Failure"] = "No active ban found on Discord."
            else:
                raise ValueError(
                    f"Attempted to deactivate an unsupported infraction #{_id} ({_type})!"
                )
        except discord.Forbidden:
            log.warning(f"Failed to deactivate infraction #{_id} ({_type}): bot lacks permissions")
            log_text["Failure"] = f"The bot lacks permissions to do this (role hierarchy?)"
        except discord.HTTPException as e:
            log.exception(f"Failed to deactivate infraction #{_id} ({_type})")
            log_text["Failure"] = f"HTTPException with code {e.code}."

        try:
            # Mark infraction as inactive in the database.
            await self.bot.api_client.patch(
                f"bot/infractions/{_id}",
                json={"active": False}
            )
        except ResponseCodeError as e:
            log.exception(f"Failed to deactivate infraction #{_id} ({_type})")
            log_line = f"API request failed with code {e.status}."

            # Append to an existing failure message if possible
            if "Failure" in log_text:
                log_text["Failure"] += f" {log_line}"
            else:
                log_text["Failure"] = log_line

        # Cancel the expiration task.
        if infraction["expires_at"] is not None:
            self.cancel_task(infraction["id"])

        # Send a log message to the mod log.
        if send_log:
            log_title = f"expiration failed" if "Failure" in log_text else "expired"

            await self.mod_log.send_log_message(
                icon_url=utils.INFRACTION_ICONS[_type][1],
                colour=Colours.soft_green,
                title=f"Infraction {log_title}: {_type}",
                text="\n".join(f"{k}: {v}" for k, v in log_text.items()),
                footer=f"ID: {_id}",
            )

        return log_text

    async def apply_infraction(
        self,
        ctx: Context,
        infraction: utils.Infraction,
        user: MemberObject,
        action_coro: t.Optional[t.Awaitable] = None
    ) -> None:
        """Apply an infraction to the user, log the infraction, and optionally notify the user."""
        infr_type = infraction["type"]
        icon = utils.INFRACTION_ICONS[infr_type][0]
        reason = infraction["reason"]
        expiry = infraction["expires_at"]

        if expiry:
            expiry = time.format_infraction(expiry)

        # Default values for the confirmation message and mod log.
        confirm_msg = f":ok_hand: applied"
        expiry_msg = f" until {expiry}" if expiry else " permanently"
        dm_result = ""
        dm_log_text = ""
        expiry_log_text = f"Expires: {expiry}" if expiry else ""
        log_title = "applied"
        log_content = None

        # DM the user about the infraction if it's not a shadow/hidden infraction.
        if not infraction["hidden"]:
            # Sometimes user is a discord.Object; make it a proper user.
            await self.bot.fetch_user(user.id)

            # Accordingly display whether the user was successfully notified via DM.
            if await utils.notify_infraction(user, infr_type, expiry, reason, icon):
                dm_result = ":incoming_envelope: "
                dm_log_text = "\nDM: Sent"
            else:
                dm_log_text = "\nDM: **Failed**"
                log_content = ctx.author.mention

        # Execute the necessary actions to apply the infraction on Discord.
        if action_coro:
            try:
                await action_coro
                if expiry:
                    # Schedule the expiration of the infraction.
                    self.schedule_task(ctx.bot.loop, infraction["id"], infraction)
            except discord.Forbidden:
                # Accordingly display that applying the infraction failed.
                confirm_msg = f":x: failed to apply"
                expiry_msg = ""
                log_content = ctx.author.mention
                log_title = "failed to apply"

        # Send a confirmation message to the invoking context.
        await ctx.send(f"{dm_result}{confirm_msg} **{infr_type}** to {user.mention}{expiry_msg}.")

        # Send a log message to the mod log.
        await self.mod_log.send_log_message(
            icon_url=icon,
            colour=Colours.soft_red,
            title=f"Infraction {log_title}: {infr_type}",
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}{dm_log_text}
                Reason: {reason}
                {expiry_log_text}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    async def pardon_infraction(self, ctx: Context, infr_type: str, user: MemberObject) -> None:
        """Prematurely end an infraction for a user and log the action in the mod log."""
        # Check the current active infraction
        response = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'active': 'true',
                'type': infr_type,
                'user__id': user.id
            }
        )

        if not response:
            await ctx.send(f":x: There's no active {infr_type} infraction for user {user.mention}.")
            return

        # Deactivate the infraction and cancel its scheduled expiration task.
        log_text = await self.deactivate_infraction(response[0], send_log=False)

        log_text["Member"] = f"{user.mention}(`{user.id}`)"
        log_text["Actor"] = str(ctx.message.author)
        log_content = None
        footer = f"ID: {response[0]['id']}"

        # If multiple active infractions were found, mark them as inactive in the database
        # and cancel their expiration tasks.
        if len(response) > 1:
            log.warning(f"Found more than one active {infr_type} infraction for user {user.id}")

            footer = f"Infraction IDs: {', '.join(str(infr['id']) for infr in response)}"
            log_text["Note"] = f"Found multiple **active** {infr_type} infractions in the database."

            # deactivate_infraction() is not called again because:
            #     1. Discord cannot store multiple active bans or assign multiples of the same role
            #     2. It would send a pardon DM for each active infraction, which is redundant
            for infraction in response[1:]:
                _id = infraction['id']
                try:
                    # Mark infraction as inactive in the database.
                    await self.bot.api_client.patch(
                        f"bot/infractions/{_id}",
                        json={"active": False}
                    )
                except ResponseCodeError:
                    log.exception(f"Failed to deactivate infraction #{_id} ({infr_type})")
                    # This is simpler and cleaner than trying to concatenate all the errors.
                    log_text["Failure"] = "See bot's logs for details."

                # Cancel pending expiration task.
                if infraction["expires_at"] is not None:
                    self.cancel_task(infraction["id"])

        # Accordingly display whether the user was successfully notified via DM.
        dm_emoji = ""
        if log_text.get("DM") == "Sent":
            dm_emoji = ":incoming_envelope: "
        elif "DM" in log_text:
            # Mention the actor because the DM failed to send.
            log_content = ctx.author.mention

        # Accordingly display whether the pardon failed.
        if "Failure" in log_text:
            confirm_msg = ":x: failed to pardon"
            log_title = "pardon failed"
            log_content = ctx.author.mention
        else:
            confirm_msg = f":ok_hand: pardoned"
            log_title = "pardoned"

        # Send a confirmation message to the invoking context.
        await ctx.send(
            f"{dm_emoji}{confirm_msg} infraction **{infr_type}** for {user.mention}. "
            f"{log_text.get('Failure', '')}"
        )

        # Send a log message to the mod log.
        await self.mod_log.send_log_message(
            icon_url=utils.INFRACTION_ICONS[infr_type][1],
            colour=Colours.soft_green,
            title=f"Infraction {log_title}: {infr_type}",
            thumbnail=user.avatar_url_as(static_format="png"),
            text="\n".join(f"{k}: {v}" for k, v in log_text.items()),
            footer=footer,
            content=log_content,
        )

    # endregion

    # This cannot be static (must have a __func__ attribute).
    def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return with_role_check(ctx, *constants.MODERATION_ROLES)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Send a notification to the invoking context on a Union failure."""
        if isinstance(error, commands.BadUnionArgument):
            if discord.User in error.converters:
                await ctx.send(str(error.errors[0]))
                error.handled = True
