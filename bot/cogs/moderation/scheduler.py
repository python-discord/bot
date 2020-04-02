import asyncio
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
from bot.constants import Colours, STAFF_CHANNELS
from bot.utils import time
from bot.utils.scheduling import Scheduler
from . import utils
from .modlog import ModLog
from .utils import UserSnowflake

log = logging.getLogger(__name__)


class InfractionScheduler(Scheduler):
    """Handles the application, pardoning, and expiration of infractions."""

    def __init__(self, bot: Bot, supported_infractions: t.Container[str]):
        super().__init__()

        self.bot = bot
        self.bot.loop.create_task(self.reschedule_infractions(supported_infractions))

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
                self.schedule_task(infraction["id"], infraction)

    async def reapply_infraction(
        self,
        infraction: utils.Infraction,
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
        await apply_coro
        log.info(f"Re-applied {infraction['type']} to user {infraction['user']} upon rejoining.")

    async def apply_infraction(
        self,
        ctx: Context,
        infraction: utils.Infraction,
        user: UserSnowflake,
        action_coro: t.Optional[t.Awaitable] = None
    ) -> None:
        """Apply an infraction to the user, log the infraction, and optionally notify the user."""
        infr_type = infraction["type"]
        icon = utils.INFRACTION_ICONS[infr_type][0]
        reason = infraction["reason"]
        expiry = time.format_infraction_with_duration(infraction["expires_at"])
        id_ = infraction['id']

        log.trace(f"Applying {infr_type} infraction #{id_} to {user}.")

        # Default values for the confirmation message and mod log.
        confirm_msg = f":ok_hand: applied"

        # Specifying an expiry for a note or warning makes no sense.
        if infr_type in ("note", "warning"):
            expiry_msg = ""
        else:
            expiry_msg = f" until {expiry}" if expiry else " permanently"

        dm_result = ""
        dm_log_text = ""
        expiry_log_text = f"Expires: {expiry}" if expiry else ""
        log_title = "applied"
        log_content = None

        # DM the user about the infraction if it's not a shadow/hidden infraction.
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
                if await utils.notify_infraction(user, infr_type, expiry, reason, icon):
                    dm_result = ":incoming_envelope: "
                    dm_log_text = "\nDM: Sent"

        if infraction["actor"] == self.bot.user.id:
            log.trace(
                f"Infraction #{id_} actor is bot; including the reason in the confirmation message."
            )

            end_msg = f" (reason: {infraction['reason']})"
        elif ctx.channel.id not in STAFF_CHANNELS:
            log.trace(
                f"Infraction #{id_} context is not in a staff channel; omitting infraction count."
            )

            end_msg = ""
        else:
            log.trace(f"Fetching total infraction count for {user}.")

            infractions = await self.bot.api_client.get(
                "bot/infractions",
                params={"user__id": str(user.id)}
            )
            total = len(infractions)
            end_msg = f" ({total} infraction{ngettext('', 's', total)} total)"

        # Execute the necessary actions to apply the infraction on Discord.
        if action_coro:
            log.trace(f"Awaiting the infraction #{id_} application action coroutine.")
            try:
                await action_coro
                if expiry:
                    # Schedule the expiration of the infraction.
                    self.schedule_task(infraction["id"], infraction)
            except discord.HTTPException as e:
                # Accordingly display that applying the infraction failed.
                confirm_msg = f":x: failed to apply"
                expiry_msg = ""
                log_content = ctx.author.mention
                log_title = "failed to apply"

                log_msg = f"Failed to apply {infr_type} infraction #{id_} to {user}"
                if isinstance(e, discord.Forbidden):
                    log.warning(f"{log_msg}: bot lacks permissions.")
                else:
                    log.exception(log_msg)

        # Send a confirmation message to the invoking context.
        log.trace(f"Sending infraction #{id_} confirmation message.")
        await ctx.send(
            f"{dm_result}{confirm_msg} **{infr_type}** to {user.mention}{expiry_msg}{end_msg}."
        )

        # Send a log message to the mod log.
        log.trace(f"Sending apply mod log for infraction #{id_}.")
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

        log.info(f"Applied {infr_type} infraction #{id_} to {user}.")

    async def pardon_infraction(self, ctx: Context, infr_type: str, user: UserSnowflake) -> None:
        """Prematurely end an infraction for a user and log the action in the mod log."""
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

        log_text["Member"] = f"{user.mention}(`{user.id}`)"
        log_text["Actor"] = str(ctx.message.author)
        log_content = None
        id_ = response[0]['id']
        footer = f"ID: {id_}"

        # If multiple active infractions were found, mark them as inactive in the database
        # and cancel their expiration tasks.
        if len(response) > 1:
            log.info(
                f"Found more than one active {infr_type} infraction for user {user.id}; "
                "deactivating the extra active infractions too."
            )

            footer = f"Infraction IDs: {', '.join(str(infr['id']) for infr in response)}"

            log_note = f"Found multiple **active** {infr_type} infractions in the database."
            if "Note" in log_text:
                log_text["Note"] = f" {log_note}"
            else:
                log_text["Note"] = log_note

            # deactivate_infraction() is not called again because:
            #     1. Discord cannot store multiple active bans or assign multiples of the same role
            #     2. It would send a pardon DM for each active infraction, which is redundant
            for infraction in response[1:]:
                id_ = infraction['id']
                try:
                    # Mark infraction as inactive in the database.
                    await self.bot.api_client.patch(
                        f"bot/infractions/{id_}",
                        json={"active": False}
                    )
                except ResponseCodeError:
                    log.exception(f"Failed to deactivate infraction #{id_} ({infr_type})")
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
            dm_emoji = f"{constants.Emojis.failmail} "

        # Accordingly display whether the pardon failed.
        if "Failure" in log_text:
            confirm_msg = ":x: failed to pardon"
            log_title = "pardon failed"
            log_content = ctx.author.mention

            log.warning(f"Failed to pardon {infr_type} infraction #{id_} for {user}.")
        else:
            confirm_msg = f":ok_hand: pardoned"
            log_title = "pardoned"

            log.info(f"Pardoned {infr_type} infraction #{id_} for {user}.")

        # Send a confirmation message to the invoking context.
        log.trace(f"Sending infraction #{id_} pardon confirmation message.")
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
            "Actor": str(self.bot.get_user(actor) or actor),
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
            log_text["Failure"] = f"The bot lacks permissions to do this (role hierarchy?)"
            log_content = mod_role.mention
        except discord.HTTPException as e:
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
            self.cancel_task(infraction["id"])

        # Send a log message to the mod log.
        if send_log:
            log_title = f"expiration failed" if "Failure" in log_text else "expired"

            user = self.bot.get_user(user_id)
            avatar = user.avatar_url_as(static_format="png") if user else None

            log.trace(f"Sending deactivation mod log for infraction #{id_}.")
            await self.mod_log.send_log_message(
                icon_url=utils.INFRACTION_ICONS[type_][1],
                colour=Colours.soft_green,
                title=f"Infraction {log_title}: {type_}",
                thumbnail=avatar,
                text="\n".join(f"{k}: {v}" for k, v in log_text.items()),
                footer=f"ID: {id_}",
                content=log_content,

            )

        return log_text

    @abstractmethod
    async def _pardon_action(self, infraction: utils.Infraction) -> t.Optional[t.Dict[str, str]]:
        """
        Execute deactivation steps specific to the infraction's type and return a log dict.

        If an infraction type is unsupported, return None instead.
        """
        raise NotImplementedError

    async def _scheduled_task(self, infraction: utils.Infraction) -> None:
        """
        Marks an infraction expired after the delay from time of scheduling to time of expiration.

        At the time of expiration, the infraction is marked as inactive on the website and the
        expiration task is cancelled.
        """
        expiry = dateutil.parser.isoparse(infraction["expires_at"]).replace(tzinfo=None)
        await time.wait_until(expiry)

        # Because deactivate_infraction() explicitly cancels this scheduled task, it is shielded
        # to avoid prematurely cancelling itself.
        await asyncio.shield(self.deactivate_infraction(infraction))
