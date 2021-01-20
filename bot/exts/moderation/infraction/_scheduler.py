import logging
import textwrap
import typing as t
from abc import abstractmethod
from datetime import datetime
from gettext import ngettext

import dateutil.parser
import discord
from discord.ext.commands import Context

from bot import constants
from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Colours
from bot.exts.moderation.infraction import _utils
from bot.exts.moderation.infraction._utils import UserSnowflake
from bot.exts.moderation.modlog import ModLog
from bot.utils import messages, scheduling, time
from bot.utils.channel import is_mod_channel

log = logging.getLogger(__name__)


class InfractionScheduler:
    """Handles the application, pardoning, and expiration of infractions."""

    def __init__(self, bot: Bot, supported_infractions: t.Container[str]):
        self.bot = bot
        self.scheduler = scheduling.Scheduler(self.__class__.__name__)

        self.bot.loop.create_task(self.reschedule_infractions(supported_infractions))

    def cog_unload(self) -> None:
        """Cancel scheduled tasks."""
        self.scheduler.cancel_all()

    @property
    def mod_log(self) -> ModLog:
        """Get the currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    async def reschedule_infractions(self, supported_infractions: t.Container[str]) -> None:
        """Schedule expiration for previous infractions."""
        await self.bot.wait_until_guild_available()

        log.trace(f"Rescheduling infractions for {self.__class__.__name__}.")

        infractions = await self.bot.api_client.get(
            'bot/infractions',
            params={'active': 'true'}
        )
        for infraction in infractions:
            if infraction["expires_at"] is not None and infraction["type"] in supported_infractions:
                self.schedule_expiration(infraction)

    async def reapply_infraction(
        self,
        infraction: _utils.Infraction,
        apply_coro: t.Optional[t.Awaitable]
    ) -> None:
        """Reapply an infraction if it's still active or deactivate it if less than 60 sec left."""
        # Calculate the time remaining, in seconds, for the mute.
        expiry = dateutil.parser.isoparse(infraction["expires_at"]).replace(tzinfo=None)
        delta = (expiry - datetime.utcnow()).total_seconds()

        # Mark as inactive if less than a minute remains.
        if delta < 60:
            log.info(
                "Infraction will be deactivated instead of re-applied "
                "because less than 1 minute remains."
            )
            await self.deactivate_infraction(infraction)
            return

        # Allowing mod log since this is a passive action that should be logged.
        try:
            await apply_coro
        except discord.HTTPException as e:
            # When user joined and then right after this left again before action completed, this can't apply roles
            if e.code == 10007 or e.status == 404:
                log.info(
                    f"Can't reapply {infraction['type']} to user {infraction['user']} because user left the guild."
                )
            else:
                log.exception(
                    f"Got unexpected HTTPException (HTTP {e.status}, Discord code {e.code})"
                    f"when awaiting {infraction['type']} coroutine for {infraction['user']}."
                )
        else:
            log.info(f"Re-applied {infraction['type']} to user {infraction['user']} upon rejoining.")

    async def apply_infraction(
        self,
        ctx: Context,
        infraction: _utils.Infraction,
        user: UserSnowflake,
        action_coro: t.Optional[t.Awaitable] = None,
        user_reason: t.Optional[str] = None,
        additional_info: str = "",
    ) -> bool:
        """
        Apply an infraction to the user, log the infraction, and optionally notify the user.

        `action_coro`, if not provided, will result in the infraction not getting scheduled for deletion.
        `user_reason`, if provided, will be sent to the user in place of the infraction reason.
        `additional_info` will be attached to the text field in the mod-log embed.

        Returns whether or not the infraction succeeded.
        """
        infr_type = infraction["type"]
        icon = _utils.INFRACTION_ICONS[infr_type][0]
        reason = infraction["reason"]
        expiry = time.format_infraction_with_duration(infraction["expires_at"])
        id_ = infraction['id']

        if user_reason is None:
            user_reason = reason

        log.trace(f"Applying {infr_type} infraction #{id_} to {user}.")

        # Default values for the confirmation message and mod log.
        confirm_msg = ":ok_hand: applied"

        # Specifying an expiry for a note or warning makes no sense.
        if infr_type in ("note", "warning"):
            expiry_msg = ""
        else:
            expiry_msg = f" until {expiry}" if expiry else " permanently"

        dm_result = ""
        dm_log_text = ""
        expiry_log_text = f"\nExpires: {expiry}" if expiry else ""
        log_title = "applied"
        log_content = None
        failed = False

        # DM the user about the infraction if it's not a shadow/hidden infraction.
        # This needs to happen before we apply the infraction, as the bot cannot
        # send DMs to user that it doesn't share a guild with. If we were to
        # apply kick/ban infractions first, this would mean that we'd make it
        # impossible for us to deliver a DM. See python-discord/bot#982.
        if not infraction["hidden"]:
            dm_result = f"{constants.Emojis.failmail} "
            dm_log_text = "\nDM: **Failed**"

            # Sometimes user is a discord.Object; make it a proper user.
            try:
                if not isinstance(user, (discord.Member, discord.User)):
                    user = await self.bot.fetch_user(user.id)
            except discord.HTTPException as e:
                log.error(f"Failed to DM {user.id}: could not fetch user (status {e.status})")
            else:
                # Accordingly display whether the user was successfully notified via DM.
                if await _utils.notify_infraction(user, infr_type.replace("_", " ").title(), expiry, user_reason, icon):
                    dm_result = ":incoming_envelope: "
                    dm_log_text = "\nDM: Sent"

        end_msg = ""
        if infraction["actor"] == self.bot.user.id:
            log.trace(
                f"Infraction #{id_} actor is bot; including the reason in the confirmation message."
            )
            if reason:
                end_msg = f" (reason: {textwrap.shorten(reason, width=1500, placeholder='...')})"
        elif is_mod_channel(ctx.channel):
            log.trace(f"Fetching total infraction count for {user}.")

            infractions = await self.bot.api_client.get(
                "bot/infractions",
                params={"user__id": str(user.id)}
            )
            total = len(infractions)
            end_msg = f" (#{id_} ; {total} infraction{ngettext('', 's', total)} total)"

        # Execute the necessary actions to apply the infraction on Discord.
        if action_coro:
            log.trace(f"Awaiting the infraction #{id_} application action coroutine.")
            try:
                await action_coro
                if expiry:
                    # Schedule the expiration of the infraction.
                    self.schedule_expiration(infraction)
            except discord.HTTPException as e:
                # Accordingly display that applying the infraction failed.
                # Don't use ctx.message.author; antispam only patches ctx.author.
                confirm_msg = ":x: failed to apply"
                expiry_msg = ""
                log_content = ctx.author.mention
                log_title = "failed to apply"

                log_msg = f"Failed to apply {' '.join(infr_type.split('_'))} infraction #{id_} to {user}"
                if isinstance(e, discord.Forbidden):
                    log.warning(f"{log_msg}: bot lacks permissions.")
                elif e.code == 10007 or e.status == 404:
                    log.info(
                        f"Can't apply {infraction['type']} to user {infraction['user']} because user left from guild."
                    )
                else:
                    log.exception(log_msg)
                failed = True

        if failed:
            log.trace(f"Deleted infraction {infraction['id']} from database because applying infraction failed.")
            try:
                await self.bot.api_client.delete(f"bot/infractions/{id_}")
            except ResponseCodeError as e:
                confirm_msg += " and failed to delete"
                log_title += " and failed to delete"
                log.error(f"Deletion of {infr_type} infraction #{id_} failed with error code {e.status}.")
            infr_message = ""
        else:
            infr_message = f" **{' '.join(infr_type.split('_'))}** to {user.mention}{expiry_msg}{end_msg}"

        # Send a confirmation message to the invoking context.
        log.trace(f"Sending infraction #{id_} confirmation message.")
        await ctx.send(f"{dm_result}{confirm_msg}{infr_message}.")

        # Send a log message to the mod log.
        # Don't use ctx.message.author for the actor; antispam only patches ctx.author.
        log.trace(f"Sending apply mod log for infraction #{id_}.")
        await self.mod_log.send_log_message(
            icon_url=icon,
            colour=Colours.soft_red,
            title=f"Infraction {log_title}: {' '.join(infr_type.split('_'))}",
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {messages.format_user(user)}
                Actor: {ctx.author.mention}{dm_log_text}{expiry_log_text}
                Reason: {reason}
                {additional_info}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

        log.info(f"Applied {infr_type} infraction #{id_} to {user}.")
        return not failed

    async def pardon_infraction(
            self,
            ctx: Context,
            infr_type: str,
            user: UserSnowflake,
            send_msg: bool = True
    ) -> None:
        """
        Prematurely end an infraction for a user and log the action in the mod log.

        If `send_msg` is True, then a pardoning confirmation message will be sent to
        the context channel.  Otherwise, no such message will be sent.
        """
        log.trace(f"Pardoning {infr_type} infraction for {user}.")

        # Check the current active infraction
        log.trace(f"Fetching active {infr_type} infractions for {user}.")
        response = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'active': 'true',
                'type': infr_type,
                'user__id': user.id
            }
        )

        if not response:
            log.debug(f"No active {infr_type} infraction found for {user}.")
            await ctx.send(f":x: There's no active {infr_type} infraction for user {user.mention}.")
            return

        # Deactivate the infraction and cancel its scheduled expiration task.
        log_text = await self.deactivate_infraction(response[0], send_log=False)

        log_text["Member"] = messages.format_user(user)
        log_text["Actor"] = ctx.author.mention
        log_content = None
        id_ = response[0]['id']
        footer = f"ID: {id_}"

        # Accordingly display whether the user was successfully notified via DM.
        dm_emoji = ""
        if log_text.get("DM") == "Sent":
            dm_emoji = ":incoming_envelope: "
        elif "DM" in log_text:
            dm_emoji = f"{constants.Emojis.failmail} "

        # Accordingly display whether the pardon failed.
        if "Failure" in log_text:
            confirm_msg = ":x: failed to pardon"
            log_title = "pardon failed"
            log_content = ctx.author.mention

            log.warning(f"Failed to pardon {infr_type} infraction #{id_} for {user}.")
        else:
            confirm_msg = ":ok_hand: pardoned"
            log_title = "pardoned"

            log.info(f"Pardoned {infr_type} infraction #{id_} for {user}.")

        # Send a confirmation message to the invoking context.
        if send_msg:
            log.trace(f"Sending infraction #{id_} pardon confirmation message.")
            await ctx.send(
                f"{dm_emoji}{confirm_msg} infraction **{' '.join(infr_type.split('_'))}** for {user.mention}. "
                f"{log_text.get('Failure', '')}"
            )

        # Move reason to end of entry to avoid cutting out some keys
        log_text["Reason"] = log_text.pop("Reason")

        # Send a log message to the mod log.
        await self.mod_log.send_log_message(
            icon_url=_utils.INFRACTION_ICONS[infr_type][1],
            colour=Colours.soft_green,
            title=f"Infraction {log_title}: {' '.join(infr_type.split('_'))}",
            thumbnail=user.avatar_url_as(static_format="png"),
            text="\n".join(f"{k}: {v}" for k, v in log_text.items()),
            footer=footer,
            content=log_content,
        )

    async def deactivate_infraction(
        self,
        infraction: _utils.Infraction,
        send_log: bool = True
    ) -> t.Dict[str, str]:
        """
        Deactivate an active infraction and return a dictionary of lines to send in a mod log.

        The infraction is removed from Discord, marked as inactive in the database, and has its
        expiration task cancelled. If `send_log` is True, a mod log is sent for the
        deactivation of the infraction.

        Infractions of unsupported types will raise a ValueError.
        """
        guild = self.bot.get_guild(constants.Guild.id)
        mod_role = guild.get_role(constants.Roles.moderators)
        user_id = infraction["user"]
        actor = infraction["actor"]
        type_ = infraction["type"]
        id_ = infraction["id"]
        inserted_at = infraction["inserted_at"]
        expiry = infraction["expires_at"]

        log.info(f"Marking infraction #{id_} as inactive (expired).")

        expiry = dateutil.parser.isoparse(expiry).replace(tzinfo=None) if expiry else None
        created = time.format_infraction_with_duration(inserted_at, expiry)

        log_content = None
        log_text = {
            "Member": f"<@{user_id}>",
            "Actor": f"<@{actor}>",
            "Reason": infraction["reason"],
            "Created": created,
        }

        try:
            log.trace("Awaiting the pardon action coroutine.")
            returned_log = await self._pardon_action(infraction)

            if returned_log is not None:
                log_text = {**log_text, **returned_log}  # Merge the logs together
            else:
                raise ValueError(
                    f"Attempted to deactivate an unsupported infraction #{id_} ({type_})!"
                )
        except discord.Forbidden:
            log.warning(f"Failed to deactivate infraction #{id_} ({type_}): bot lacks permissions.")
            log_text["Failure"] = "The bot lacks permissions to do this (role hierarchy?)"
            log_content = mod_role.mention
        except discord.HTTPException as e:
            if e.code == 10007 or e.status == 404:
                log.info(
                    f"Can't pardon {infraction['type']} for user {infraction['user']} because user left the guild."
                )
                log_text["Failure"] = "User left the guild."
                log_content = mod_role.mention
            else:
                log.exception(f"Failed to deactivate infraction #{id_} ({type_})")
                log_text["Failure"] = f"HTTPException with status {e.status} and code {e.code}."
                log_content = mod_role.mention

        # Check if the user is currently being watched by Big Brother.
        try:
            log.trace(f"Determining if user {user_id} is currently being watched by Big Brother.")

            active_watch = await self.bot.api_client.get(
                "bot/infractions",
                params={
                    "active": "true",
                    "type": "watch",
                    "user__id": user_id
                }
            )

            log_text["Watching"] = "Yes" if active_watch else "No"
        except ResponseCodeError:
            log.exception(f"Failed to fetch watch status for user {user_id}")
            log_text["Watching"] = "Unknown - failed to fetch watch status."

        try:
            # Mark infraction as inactive in the database.
            log.trace(f"Marking infraction #{id_} as inactive in the database.")
            await self.bot.api_client.patch(
                f"bot/infractions/{id_}",
                json={"active": False}
            )
        except ResponseCodeError as e:
            log.exception(f"Failed to deactivate infraction #{id_} ({type_})")
            log_line = f"API request failed with code {e.status}."
            log_content = mod_role.mention

            # Append to an existing failure message if possible
            if "Failure" in log_text:
                log_text["Failure"] += f" {log_line}"
            else:
                log_text["Failure"] = log_line

        # Cancel the expiration task.
        if infraction["expires_at"] is not None:
            self.scheduler.cancel(infraction["id"])

        # Send a log message to the mod log.
        if send_log:
            log_title = "expiration failed" if "Failure" in log_text else "expired"

            user = self.bot.get_user(user_id)
            avatar = user.avatar_url_as(static_format="png") if user else None

            # Move reason to end so when reason is too long, this is not gonna cut out required items.
            log_text["Reason"] = log_text.pop("Reason")

            log.trace(f"Sending deactivation mod log for infraction #{id_}.")
            await self.mod_log.send_log_message(
                icon_url=_utils.INFRACTION_ICONS[type_][1],
                colour=Colours.soft_green,
                title=f"Infraction {log_title}: {type_}",
                thumbnail=avatar,
                text="\n".join(f"{k}: {v}" for k, v in log_text.items()),
                footer=f"ID: {id_}",
                content=log_content,
            )

        return log_text

    @abstractmethod
    async def _pardon_action(self, infraction: _utils.Infraction) -> t.Optional[t.Dict[str, str]]:
        """
        Execute deactivation steps specific to the infraction's type and return a log dict.

        If an infraction type is unsupported, return None instead.
        """
        raise NotImplementedError

    def schedule_expiration(self, infraction: _utils.Infraction) -> None:
        """
        Marks an infraction expired after the delay from time of scheduling to time of expiration.

        At the time of expiration, the infraction is marked as inactive on the website and the
        expiration task is cancelled.
        """
        expiry = dateutil.parser.isoparse(infraction["expires_at"]).replace(tzinfo=None)
        self.scheduler.schedule_at(expiry, infraction["id"], self.deactivate_infraction(infraction))
