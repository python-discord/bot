import logging
import textwrap
import typing as t
from abc import abstractmethod
from datetime import datetime
from gettext import ngettext

import dateutil.parser
import discord
from discord.ext.commands import Bot, Context

from bot import constants
from bot.api import ResponseCodeError
from bot.constants import Colours, STAFF_CHANNELS
from bot.utils import time
from bot.utils.scheduling import Scheduler
from . import utils
from .modlog import ModLog
from .utils import MemberObject

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
        await self.bot.wait_until_ready()

        infractions = await self.bot.api_client.get(
            'bot/infractions',
            params={'active': 'true'}
        )
        for infraction in infractions:
            if infraction["expires_at"] is not None and infraction["type"] in supported_infractions:
                self.schedule_task(self.bot.loop, infraction["id"], infraction)

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
            await self.deactivate_infraction(infraction)
            return

        # Allowing mod log since this is a passive action that should be logged.
        await apply_coro
        log.info(f"Re-applied {infraction['type']} to user {infraction['user']} upon rejoining.")

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
            # Sometimes user is a discord.Object; make it a proper user.
            user = await self.bot.fetch_user(user.id)

            # Accordingly display whether the user was successfully notified via DM.
            if await utils.notify_infraction(user, infr_type, expiry, reason, icon):
                dm_result = ":incoming_envelope: "
                dm_log_text = "\nDM: Sent"
            else:
                dm_log_text = "\nDM: **Failed**"
                log_content = ctx.author.mention

        if infraction["actor"] == self.bot.user.id:
            end_msg = f" (reason: {infraction['reason']})"
        elif ctx.channel.id not in STAFF_CHANNELS:
            end_msg = ""
        else:
            infractions = await self.bot.api_client.get(
                "bot/infractions",
                params={"user__id": str(user.id)}
            )
            total = len(infractions)
            end_msg = f" ({total} infraction{ngettext('', 's', total)} total)"

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
        await ctx.send(
            f"{dm_result}{confirm_msg} **{infr_type}** to {user.mention}{expiry_msg}{end_msg}."
        )

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

            log_note = f"Found multiple **active** {infr_type} infractions in the database."
            if "Note" in log_text:
                log_text["Note"] = f" {log_note}"
            else:
                log_text["Note"] = log_note

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
        mod_role = guild.get_role(constants.Roles.moderator)
        user_id = infraction["user"]
        _type = infraction["type"]
        _id = infraction["id"]

        log.debug(f"Marking infraction #{_id} as inactive (expired).")

        log_content = None
        log_text = {
            "Member": str(user_id),
            "Actor": str(self.bot.user),
            "Reason": infraction["reason"]
        }

        try:
            returned_log = await self._pardon_action(infraction)
            if returned_log is not None:
                log_text = {**log_text, **returned_log}  # Merge the logs together
            else:
                raise ValueError(
                    f"Attempted to deactivate an unsupported infraction #{_id} ({_type})!"
                )
        except discord.Forbidden:
            log.warning(f"Failed to deactivate infraction #{_id} ({_type}): bot lacks permissions")
            log_text["Failure"] = f"The bot lacks permissions to do this (role hierarchy?)"
            log_content = mod_role.mention
        except discord.HTTPException as e:
            log.exception(f"Failed to deactivate infraction #{_id} ({_type})")
            log_text["Failure"] = f"HTTPException with code {e.code}."
            log_content = mod_role.mention

        # Check if the user is currently being watched by Big Brother.
        try:
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
            await self.bot.api_client.patch(
                f"bot/infractions/{_id}",
                json={"active": False}
            )
        except ResponseCodeError as e:
            log.exception(f"Failed to deactivate infraction #{_id} ({_type})")
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

            await self.mod_log.send_log_message(
                icon_url=utils.INFRACTION_ICONS[_type][1],
                colour=Colours.soft_green,
                title=f"Infraction {log_title}: {_type}",
                text="\n".join(f"{k}: {v}" for k, v in log_text.items()),
                footer=f"ID: {_id}",
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

        await self.deactivate_infraction(infraction)
