import textwrap
import typing as t
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from gettext import ngettext

import arrow
import dateutil.parser
import discord
from async_rediscache import RedisCache
from discord.ext.commands import Context
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils import scheduling

from bot import constants
from bot.bot import Bot
from bot.constants import Colours, Roles
from bot.converters import MemberOrUser
from bot.exts.moderation.infraction import _utils
from bot.exts.moderation.modlog import ModLog
from bot.log import get_logger
from bot.utils import messages, time
from bot.utils.channel import is_mod_channel
from bot.utils.modlog import send_log_message

log = get_logger(__name__)

AUTOMATED_TIDY_UP_HOURS = 1

# Error when trying to delete a message in an archived thread.
ARCHIVED_THREAD_ERROR = 50083

class InfractionScheduler:
    """Handles the application, pardoning, and expiration of infractions."""

    messages_to_tidy: RedisCache = RedisCache()

    def __init__(self, bot: Bot, supported_infractions: t.Container[str]):
        self.bot = bot
        self.scheduler = scheduling.Scheduler(self.__class__.__name__)
        self.tidy_up_scheduler = scheduling.Scheduler(
            f"{self.__class__.__name__}TidyUp"
        )
        self.supported_infractions = supported_infractions

    async def cog_unload(self) -> None:
        """Cancel scheduled tasks."""
        self.scheduler.cancel_all()
        self.tidy_up_scheduler.cancel_all()

    @property
    def mod_log(self) -> ModLog:
        """Get the currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    async def cog_load(self) -> None:
        """Schedule expiration for previous infractions."""
        await self.bot.wait_until_guild_available()
        supported_infractions = self.supported_infractions

        log.trace(f"Rescheduling infractions for {self.__class__.__name__}.")

        infractions = await self.bot.api_client.get(
            "bot/infractions",
            params={
                "active": "true",
                "ordering": "expires_at",
                "permanent": "false",
                "types": ",".join(supported_infractions),
            },
        )

        to_schedule = [i for i in infractions if i["id"] not in self.scheduler]

        for infraction in to_schedule:
            log.trace("Scheduling %r", infraction)
            self.schedule_expiration(infraction)

        # Call ourselves again when the last infraction would expire. This will be the "oldest" infraction we've seen
        # from the database so far, and new ones are scheduled as part of application.
        # We make sure to fire this
        if to_schedule:
            next_reschedule_point = max(
                dateutil.parser.isoparse(infr["expires_at"]) for infr in to_schedule
            )
            log.trace("Will reschedule remaining infractions at %s", next_reschedule_point)

            self.scheduler.schedule_at(next_reschedule_point, -1, self.cog_load())

        log.trace("Done rescheduling expirations, scheduling tidy up tasks.")

        for key, expire_at in await self.messages_to_tidy.items():
            channel_id, message_id = map(int, key.split(":"))
            expire_at = dateutil.parser.isoparse(expire_at)

            log.trace(
                "Scheduling tidy up for message %s in channel %s at %s",
                message_id, channel_id, expire_at
            )

            self.tidy_up_scheduler.schedule_at(
                expire_at,
                message_id,
                self._delete_infraction_message(channel_id, message_id)
            )

    async def _delete_infraction_message(
        self,
        channel_id: int,
        message_id: int
    ) -> None:
        """
        Delete a message in the given channel.

        This is used to delete infraction messages after a certain period of time.
        """
        try:
            partial_channel = self.bot.get_partial_messageable(channel_id)
            partial_message = partial_channel.get_partial_message(message_id)
            await partial_message.delete()
            log.trace(f"Deleted infraction message {message_id} in channel {channel_id}.")
        except discord.NotFound:
            log.info(f"Channel or message {message_id} not found in channel {channel_id}.")
        except discord.Forbidden:
            log.info(f"Bot lacks permissions to delete message {message_id} in channel {channel_id}.")
        except discord.HTTPException as e:
            if e.code == ARCHIVED_THREAD_ERROR:
                log.info(
                    f"Cannot delete message {message_id} in channel {channel_id} because the thread is archived."
                )
            else:
                log.exception(f"Issue during scheduled deletion of message {message_id} in channel {channel_id}.")
                return  # Keep the task in Redis on HTTP errors

        await self.messages_to_tidy.delete(f"{channel_id}:{message_id}")

    async def reapply_infraction(
        self,
        infraction: _utils.Infraction,
        action: Callable[[], Awaitable[None]] | None
    ) -> None:
        """
        Reapply an infraction if it's still active or deactivate it if less than 60 sec left.

        Note: The `action` provided is an async function rather than a coroutine
        to prevent getting a RuntimeWarning if it is not used (e.g. in mocked tests).
        """
        if infraction["expires_at"] is not None:
            # Calculate the time remaining, in seconds, for the infraction.
            expiry = dateutil.parser.isoparse(infraction["expires_at"])
            delta = (expiry - arrow.utcnow()).total_seconds()
        else:
            # If the infraction is permanent, it is not possible to get the time remaining.
            delta = None

        # Mark as inactive if the infraction is not permanent and less than a minute remains.
        if delta is not None and delta < 60:
            log.info(
                "Infraction will be deactivated instead of re-applied "
                "because less than 1 minute remains."
            )
            await self.deactivate_infraction(infraction)
            return

        # Allowing mod log since this is a passive action that should be logged.
        try:
            await action()
        except discord.HTTPException as e:
            # When user joined and then right after this left again before action completed, this can't apply roles
            if e.code == 10007 or e.status == 404:
                log.info(
                    f"Can't reapply {infraction['type']} to user {infraction['user']} because user left the guild."
                )
            else:
                log.exception(
                    f"Got unexpected HTTPException (HTTP {e.status}, Discord code {e.code})"
                    f"when running {infraction['type']} action for {infraction['user']}."
                )
        else:
            log.info(f"Re-applied {infraction['type']} to user {infraction['user']} upon rejoining.")

    async def _attempt_dm(
        self,
        infraction: _utils.Infraction,
        user: MemberOrUser,
        user_reason: str | None,
    ) -> tuple[str, str]:
        """Try to DM the user about the infraction, returning (dm_result, dm_log_text)."""
        if await _utils.notify_infraction(infraction, user, user_reason):
            return ":incoming_envelope: ", "\nDM: Sent"
        return f"{constants.Emojis.failmail} ", "\nDM: **Failed**"

    @staticmethod
    def _format_infraction_data(infraction: _utils.Infraction) -> tuple:
        """Extract and format basic infraction data."""
        return (
            infraction["type"],
            _utils.INFRACTION_ICONS[infraction["type"]][0],
            infraction["reason"],
            infraction["id"],
            infraction["jump_url"],
            time.format_with_duration(infraction["expires_at"], infraction["last_applied"]),
        )

    async def _build_end_message(
        self,
        ctx: Context,
        user: MemberOrUser,
        id_: int,
        reason: str | None,
        infraction: _utils.Infraction,
    ) -> str:
        """Build the end message for the confirmation, based on channel type or actor."""
        if is_mod_channel(ctx.channel):
            log.trace(f"Fetching total infraction count for {user}.")
            infractions = await self.bot.api_client.get(
                "bot/infractions",
                params={"user__id": str(user.id)},
            )
            total = len(infractions)
            return f" (#{id_} ; {total} infraction{ngettext('', 's', total)} total)"

        if infraction["actor"] == self.bot.user.id and reason:
            log.trace(f"Infraction #{id_} actor is bot; including the reason in the confirmation message.")
            return (
                f" (reason: {textwrap.shorten(reason, width=1500, placeholder='...')})."
                f"\n\nThe <@&{Roles.moderators}> have been alerted for review"
            )

        return ""

    async def _execute_action(
        self,
        ctx: Context,
        action: Callable[[], Awaitable[None]],
        infraction: _utils.Infraction,
        user: MemberOrUser,
        infr_type: str,
        id_: int,
        expiry: str | None,
        confirm_msg: str,
        expiry_msg: str,
        log_title: str,
    ) -> tuple:
        """Execute the infraction action and return updated state."""
        log.trace(f"Running the infraction #{id_} application action.")
        try:
            await action()
            if expiry:
                self.schedule_expiration(infraction)
            return confirm_msg, expiry_msg, None, log_title, False
        except discord.HTTPException as e:
            confirm_msg = ":x: failed to apply"
            expiry_msg = ""
            log_content = ctx.author.mention
            log_title = "failed to apply"
            log_msg = f"Failed to apply {' '.join(infr_type.split('_'))} infraction #{id_} to {user}"
            if isinstance(e, discord.Forbidden):
                log.warning(f"{log_msg}: bot lacks permissions.")
            elif e.code == 10007 or e.status == 404:
                log.info(f"Can't apply {infraction['type']} to user {infraction['user']} because user left from guild.")
            else:
                log.exception(log_msg)
            return confirm_msg, expiry_msg, log_content, log_title, True

    async def _handle_failure_cleanup(
        self,
        id_: int,
        infr_type: str,
        confirm_msg: str,
        log_title: str,
    ) -> tuple[str, str]:
        """Delete the infraction from the database when the application failed."""
        log.trace(f"Trying to delete infraction {id_} from database because applying infraction failed.")
        try:
            await self.bot.api_client.delete(f"bot/infractions/{id_}")
        except ResponseCodeError as e:
            confirm_msg += " and failed to delete"
            log_title += " and failed to delete"
            log.error(f"Deletion of {infr_type} infraction #{id_} failed with error code {e.status}.")
        return confirm_msg, log_title

    async def _schedule_tidy_up(
        self,
        ctx: Context,
        sent_msg: discord.Message,
        infraction: _utils.Infraction,
        id_: int,
    ) -> None:
        """Schedule deletion of the confirmation message and persist to Redis."""
        if infraction["actor"] == self.bot.user.id and not is_mod_channel(ctx.channel):
            expire_message_time = datetime.now(UTC) + timedelta(hours=AUTOMATED_TIDY_UP_HOURS)
            log.trace(f"Scheduling message tidy for infraction #{id_} in {AUTOMATED_TIDY_UP_HOURS} hours.")
            self.tidy_up_scheduler.schedule_at(
                expire_message_time,
                sent_msg.id,
                self._delete_infraction_message(ctx.channel.id, sent_msg.id),
            )
            await self.messages_to_tidy.set(
                f"{ctx.channel.id}:{sent_msg.id}",
                expire_message_time.isoformat(),
            )

    @staticmethod
    def _build_expiry_messages(infr_type: str, expiry: str | None) -> tuple[str, str]:
        """Build the expiry message and log text based on infraction type."""
        if infr_type in ("kick", "note", "warning"):
            expiry_msg = ""
        else:
            expiry_msg = f" until {expiry}" if expiry else " permanently"

        expiry_log_text = f"\nExpires: {expiry}" if expiry else ""
        return expiry_msg, expiry_log_text

    @staticmethod
    def _format_jump_url(jump_url: str | None) -> str:
        """Format the jump URL for the mod-log embed."""
        if jump_url is None:
            return "(Infraction issued in a ModMail channel.)"
        return f"[Click here.]({jump_url})"

    async def apply_infraction(
        self,
        ctx: Context,
        infraction: _utils.Infraction,
        user: MemberOrUser,
        action: Callable[[], Awaitable[None]] | None = None,
        user_reason: str | None = None,
        additional_info: str = "",
    ) -> bool:
        """
        Apply an infraction to the user, log the infraction, and optionally notify the user.

        `action`, if not provided, will result in the infraction not getting scheduled for deletion.
        `user_reason`, if provided, will be sent to the user in place of the infraction reason.
        `additional_info` will be attached to the text field in the mod-log embed.

        Note: The `action` provided is an async function rather than just a coroutine
        to prevent getting a RuntimeWarning if it is not used (e.g. in mocked tests).

        Returns whether or not the infraction succeeded.
        """
        infr_type, icon, reason, id_, jump_url, expiry = self._format_infraction_data(infraction)

        if user_reason is None:
            user_reason = reason

        log.trace(f"Applying {infr_type} infraction #{id_} to {user}.")

        expiry_msg, expiry_log_text = self._build_expiry_messages(infr_type, expiry)
        dm_result = dm_log_text = ""
        confirm_msg, log_title, log_content, failed = ":ok_hand: applied", "applied", None, False

        if not infraction["hidden"] and infr_type in {"ban", "kick"}:
            dm_result, dm_log_text = await self._attempt_dm(infraction, user, user_reason)

        end_msg = await self._build_end_message(ctx, user, id_, reason, infraction)
        purge = infraction.get("purge", "")

        if action:
            confirm_msg, expiry_msg, log_content, log_title, failed = await self._execute_action(
                ctx, action, infraction, user, infr_type, id_, expiry,
                confirm_msg, expiry_msg, log_title,
            )

        if not failed:
            infr_message = f" **{purge}{' '.join(infr_type.split('_'))}** to {user.mention}{expiry_msg}{end_msg}"
            if not infraction["hidden"] and infr_type not in {"ban", "kick"}:
                dm_result, dm_log_text = await self._attempt_dm(infraction, user, user_reason)
                if dm_log_text == "\nDM: **Failed**" and infr_type == "warning" and not ctx.channel.permissions_for(user).view_channel:
                    failed = True
                    log_title = "failed to apply"
                    additional_info += "\n*Failed to show the warning to the user*"
                    confirm_msg = (f":x: Failed to apply **warning** to {user.mention} "
                                   "because DMing the user was unsuccessful")

        if failed:
            confirm_msg, log_title = await self._handle_failure_cleanup(id_, infr_type, confirm_msg, log_title)
            infr_message = ""

        log.trace(f"Sending infraction #{id_} confirmation message.")
        mentions = discord.AllowedMentions(users=[user], roles=False)
        sent_msg = await ctx.send(f"{dm_result}{confirm_msg}{infr_message}.", allowed_mentions=mentions)

        await self._schedule_tidy_up(ctx, sent_msg, infraction, id_)

        jump_url = self._format_jump_url(jump_url)

        log.trace(f"Sending apply mod log for infraction #{id_}.")
        await send_log_message(
            self.bot,
            icon_url=icon,
            colour=Colours.soft_red,
            title=f"Infraction {log_title}: {' '.join(infr_type.split('_'))}",
            thumbnail=user.display_avatar.url,
            text=textwrap.dedent(f"""
                Member: {messages.format_user(user)}
                Actor: {ctx.author.mention}{dm_log_text}{expiry_log_text}
                Reason: {reason}
                Jump URL: {jump_url}
                {additional_info}
            """),
            content=log_content,
            footer=f"ID: {id_}"
        )

        log.info(f"{'Failed to apply' if failed else 'Applied'} {purge}{infr_type} infraction #{id_} to {user}.")
        return not failed

    async def pardon_infraction(
        self,
        ctx: Context,
        infr_type: str,
        user: MemberOrUser,
        pardon_reason: str | None = None,
        *,
        send_msg: bool = True,
        notify: bool = True
    ) -> None:
        """
        Prematurely end an infraction for a user and log the action in the mod log.

        If `pardon_reason` is None, then the database will not receive
        appended text explaining why the infraction was pardoned.

        If `send_msg` is True, then a pardoning confirmation message will be sent to
        the context channel. Otherwise, no such message will be sent.

        If `notify` is True, notify the user of the pardon via DM where applicable.
        """
        log.trace(f"Pardoning {infr_type} infraction for {user}.")

        # Check the current active infraction
        log.trace(f"Fetching active {infr_type} infractions for {user}.")
        response = await self.bot.api_client.get(
            "bot/infractions",
            params={
                "active": "true",
                "type": infr_type,
                "user__id": user.id
            }
        )

        if not response:
            log.debug(f"No active {infr_type} infraction found for {user}.")
            await ctx.send(f":x: There's no active {infr_type} infraction for user {user.mention}.")
            return

        # Deactivate the infraction and cancel its scheduled expiration task.
        log_text = await self.deactivate_infraction(response[0], pardon_reason, send_log=False, notify=notify)

        log_text["Member"] = messages.format_user(user)
        log_text["Actor"] = ctx.author.mention
        log_content = None
        id_ = response[0]["id"]
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
        await send_log_message(
            self.bot,
            icon_url=_utils.INFRACTION_ICONS[infr_type][1],
            colour=Colours.soft_green,
            title=f"Infraction {log_title}: {' '.join(infr_type.split('_'))}",
            thumbnail=user.display_avatar.url,
            text="\n".join(f"{k}: {v}" for k, v in log_text.items()),
            footer=footer,
            content=log_content,
        )

    async def _execute_pardon_action(
        self,
        infraction: _utils.Infraction,
        notify: bool,
        log_text: dict[str, str],
        id_: int,
        type_: str,
        log_content: str | None,
        mod_role: discord.Role,
    ) -> tuple[dict[str, str], str | None]:
        """Execute the pardon action and handle Discord API errors."""
        try:
            log.trace("Awaiting the pardon action coroutine.")
            returned_log = await self._pardon_action(infraction, notify)

            if returned_log is not None:
                log_text = {**log_text, **returned_log}
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

        return log_text, log_content

    async def _check_watch_status(
        self,
        user_id: int,
        log_text: dict[str, str],
    ) -> dict[str, str]:
        """Check if the user is currently being watched by Big Brother."""
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

        return log_text

    async def _deactivate_in_database(
        self,
        id_: int,
        pardon_reason: str | None,
        infraction: _utils.Infraction,
        log_text: dict[str, str],
        log_content: str | None,
        mod_role: discord.Role,
    ) -> tuple[dict[str, str], str | None]:
        """Mark the infraction as inactive in the database."""
        try:
            log.trace(f"Marking infraction #{id_} as inactive in the database.")

            data = {"active": False}

            if pardon_reason is not None:
                data["reason"] = ""
                if (punish_reason := infraction["reason"]) is not None:
                    data["reason"] = punish_reason + " | "

                data["reason"] += f"Pardoned: {pardon_reason}"

            await self.bot.api_client.patch(
                f"bot/infractions/{id_}",
                json=data
            )
        except ResponseCodeError as e:
            log.exception(f"Failed to deactivate infraction #{id_} ({infraction['type']})")
            log_line = f"API request failed with code {e.status}."
            log_content = mod_role.mention

            if "Failure" in log_text:
                log_text["Failure"] += f" {log_line}"
            else:
                log_text["Failure"] = log_line

        return log_text, log_content

    async def deactivate_infraction(
        self,
        infraction: _utils.Infraction,
        pardon_reason: str | None = None,
        *,
        send_log: bool = True,
        notify: bool = True
    ) -> dict[str, str]:
        """
        Deactivate an active infraction and return a dictionary of lines to send in a mod log.

        The infraction is removed from Discord, marked as inactive in the database, and has its
        expiration task cancelled.

        If `pardon_reason` is None, then the database will not receive
        appended text explaining why the infraction was pardoned.

        If `send_log` is True, a mod log is sent for the deactivation of the infraction.

        If `notify` is True, notify the user of the pardon via DM where applicable.

        Infractions of unsupported types will raise a ValueError.
        """
        guild = self.bot.get_guild(constants.Guild.id)
        mod_role = guild.get_role(constants.Roles.moderators)
        user_id = infraction["user"]
        actor = infraction["actor"]
        type_ = infraction["type"]
        id_ = infraction["id"]

        log.info(f"Marking infraction #{id_} as inactive (expired).")

        log_content = None
        log_text = {
            "Member": f"<@{user_id}>",
            "Actor": f"<@{actor}>",
            "Reason": infraction["reason"],
            "Created": time.format_with_duration(infraction["inserted_at"], infraction["expires_at"]),
        }

        log_text, log_content = await self._execute_pardon_action(infraction, notify, log_text, id_, type_, log_content, mod_role)
        log_text = await self._check_watch_status(user_id, log_text)
        log_text, log_content = await self._deactivate_in_database(id_, pardon_reason, infraction, log_text, log_content, mod_role)

        # Cancel the expiration task.
        if infraction["expires_at"] is not None:
            self.scheduler.cancel(infraction["id"])

        # Send a log message to the mod log.
        if send_log:
            log_title = "expiration failed" if "Failure" in log_text else "expired"

            user = self.bot.get_user(user_id)
            avatar = user.display_avatar.url if user else None

            log_text["Reason"] = log_text.pop("Reason")

            log.trace(f"Sending deactivation mod log for infraction #{id_}.")
            await send_log_message(
                self.bot,
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
    async def _pardon_action(
        self,
        infraction: _utils.Infraction,
        notify: bool
    ) -> dict[str, str] | None:
        """
        Execute deactivation steps specific to the infraction's type and return a log dict.

        If `notify` is True, notify the user of the pardon via DM where applicable.
        If an infraction type is unsupported, return None instead.
        """
        raise NotImplementedError

    def schedule_expiration(self, infraction: _utils.Infraction) -> None:
        """
        Marks an infraction expired after the delay from time of scheduling to time of expiration.

        At the time of expiration, the infraction is marked as inactive on the website and the
        expiration task is cancelled.
        """
        expiry = dateutil.parser.isoparse(infraction["expires_at"])
        self.scheduler.schedule_at(expiry, infraction["id"], self.deactivate_infraction(infraction))
