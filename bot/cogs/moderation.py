import asyncio
import logging
import textwrap
from datetime import datetime
from typing import Dict, Iterable, Optional, Union

from discord import (
    Colour, Embed, Forbidden, Guild, HTTPException, Member, NotFound, Object, User
)
from discord.ext.commands import (
    BadArgument, BadUnionArgument, Bot, Cog, Context, command, group
)

from bot import constants
from bot.cogs.modlog import ModLog
from bot.constants import Colours, Event, Icons, MODERATION_ROLES
from bot.converters import Duration, InfractionSearchQuery
from bot.decorators import respect_role_hierarchy, with_role
from bot.pagination import LinePaginator
from bot.utils.moderation import already_has_active_infraction, post_infraction
from bot.utils.scheduling import Scheduler
from bot.utils.time import INFRACTION_FORMAT, format_infraction, wait_until

log = logging.getLogger(__name__)

INFRACTION_ICONS = {
    "Mute": Icons.user_mute,
    "Kick": Icons.sign_out,
    "Ban": Icons.user_ban,
    "Warning": Icons.user_warn,
    "Note": Icons.user_warn,
}
RULES_URL = "https://pythondiscord.com/pages/rules"
APPEALABLE_INFRACTIONS = ("Ban", "Mute")


def proxy_user(user_id: str) -> Object:
    """Create a proxy user for the provided user_id for situations where a Member or User object cannot be resolved."""
    try:
        user_id = int(user_id)
    except ValueError:
        raise BadArgument
    user = Object(user_id)
    user.mention = user.id
    user.avatar_url_as = lambda static_format: None
    return user


def permanent_duration(expires_at: str) -> str:
    """Only allow an expiration to be 'permanent' if it is a string."""
    expires_at = expires_at.lower()
    if expires_at != "permanent":
        raise BadArgument
    else:
        return expires_at


UserConverter = Union[Member, User, proxy_user]
UserObject = Union[Member, User, Object]
Infraction = Dict[str, Union[str, int, bool]]


class Moderation(Scheduler, Cog):
    """Server moderation tools."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._muted_role = Object(constants.Roles.muted)
        super().__init__()

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @Cog.listener()
    async def on_ready(self) -> None:
        """Schedule expiration for previous infractions."""
        # Schedule expiration for previous infractions
        infractions = await self.bot.api_client.get(
            'bot/infractions', params={'active': 'true'}
        )
        for infraction in infractions:
            if infraction["expires_at"] is not None:
                self.schedule_task(self.bot.loop, infraction["id"], infraction)

    # region: Permanent infractions

    @with_role(*MODERATION_ROLES)
    @command()
    async def warn(self, ctx: Context, user: UserConverter, *, reason: str = None) -> None:
        """Create a warning infraction in the database for a user."""
        infraction = await post_infraction(ctx, user, type="warning", reason=reason)
        if infraction is None:
            return

        notified = await self.notify_infraction(user=user, infr_type="Warning", reason=reason)

        dm_result = ":incoming_envelope: " if notified else ""
        action = f"{dm_result}:ok_hand: warned {user.mention}"
        await ctx.send(f"{action}.")

        if notified:
            dm_status = "Sent"
            log_content = None
        else:
            dm_status = "**Failed**"
            log_content = ctx.author.mention

        await self.mod_log.send_log_message(
            icon_url=Icons.user_warn,
            colour=Colour(Colours.soft_red),
            title="Member warned",
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.author}
                DM: {dm_status}
                Reason: {reason}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    @with_role(*MODERATION_ROLES)
    @command()
    @respect_role_hierarchy()
    async def kick(self, ctx: Context, user: Member, *, reason: str = None) -> None:
        """Kicks a user with the provided reason."""
        infraction = await post_infraction(ctx, user, type="kick", reason=reason)
        if infraction is None:
            return

        notified = await self.notify_infraction(user=user, infr_type="Kick", reason=reason)

        self.mod_log.ignore(Event.member_remove, user.id)

        try:
            await user.kick(reason=reason)
            action_result = True
        except Forbidden:
            action_result = False

        dm_result = ":incoming_envelope: " if notified else ""
        action = f"{dm_result}:ok_hand: kicked {user.mention}"
        await ctx.send(f"{action}.")

        dm_status = "Sent" if notified else "**Failed**"
        title = "Member kicked" if action_result else "Member kicked (Failed)"
        log_content = None if all((notified, action_result)) else ctx.author.mention

        await self.mod_log.send_log_message(
            icon_url=Icons.sign_out,
            colour=Colour(Colours.soft_red),
            title=title,
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                DM: {dm_status}
                Reason: {reason}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    @with_role(*MODERATION_ROLES)
    @command()
    @respect_role_hierarchy()
    async def ban(self, ctx: Context, user: UserConverter, *, reason: str = None) -> None:
        """Create a permanent ban infraction for a user with the provided reason."""
        if await already_has_active_infraction(ctx=ctx, user=user, type="ban"):
            return

        infraction = await post_infraction(ctx, user, type="ban", reason=reason)
        if infraction is None:
            return

        notified = await self.notify_infraction(
            user=user,
            infr_type="Ban",
            reason=reason
        )

        self.mod_log.ignore(Event.member_ban, user.id)
        self.mod_log.ignore(Event.member_remove, user.id)

        try:
            await ctx.guild.ban(user, reason=reason, delete_message_days=0)
            action_result = True
        except Forbidden:
            action_result = False

        dm_result = ":incoming_envelope: " if notified else ""
        action = f"{dm_result}:ok_hand: permanently banned {user.mention}"
        await ctx.send(f"{action}.")

        dm_status = "Sent" if notified else "**Failed**"
        log_content = None if all((notified, action_result)) else ctx.author.mention
        title = "Member permanently banned"
        if not action_result:
            title += " (Failed)"

        await self.mod_log.send_log_message(
            icon_url=Icons.user_ban,
            colour=Colour(Colours.soft_red),
            title=title,
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                DM: {dm_status}
                Reason: {reason}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    # endregion
    # region: Temporary infractions

    @with_role(*MODERATION_ROLES)
    @command(aliases=('mute',))
    async def tempmute(self, ctx: Context, user: Member, duration: Duration, *, reason: str = None) -> None:
        """
        Create a temporary mute infraction for a user with the provided expiration and reason.

        Duration strings are parsed per: http://strftime.org/
        """
        expiration = duration

        if await already_has_active_infraction(ctx=ctx, user=user, type="mute"):
            return

        infraction = await post_infraction(ctx, user, type="mute", reason=reason, expires_at=expiration)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_update, user.id)
        await user.add_roles(self._muted_role, reason=reason)

        notified = await self.notify_infraction(
            user=user,
            infr_type="Mute",
            expires_at=expiration,
            reason=reason
        )

        infraction_expiration = format_infraction(infraction["expires_at"])

        self.schedule_task(ctx.bot.loop, infraction["id"], infraction)

        dm_result = ":incoming_envelope: " if notified else ""
        action = f"{dm_result}:ok_hand: muted {user.mention} until {infraction_expiration}"
        await ctx.send(f"{action}.")

        if notified:
            dm_status = "Sent"
            log_content = None
        else:
            dm_status = "**Failed**"
            log_content = ctx.author.mention

        await self.mod_log.send_log_message(
            icon_url=Icons.user_mute,
            colour=Colour(Colours.soft_red),
            title="Member temporarily muted",
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                DM: {dm_status}
                Reason: {reason}
                Expires: {infraction_expiration}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    @with_role(*MODERATION_ROLES)
    @command()
    @respect_role_hierarchy()
    async def tempban(self, ctx: Context, user: UserConverter, duration: Duration, *, reason: str = None) -> None:
        """
        Create a temporary ban infraction for a user with the provided expiration and reason.

        Duration strings are parsed per: http://strftime.org/
        """
        expiration = duration

        if await already_has_active_infraction(ctx=ctx, user=user, type="ban"):
            return

        infraction = await post_infraction(ctx, user, type="ban", reason=reason, expires_at=expiration)
        if infraction is None:
            return

        notified = await self.notify_infraction(
            user=user,
            infr_type="Ban",
            expires_at=expiration,
            reason=reason
        )

        self.mod_log.ignore(Event.member_ban, user.id)
        self.mod_log.ignore(Event.member_remove, user.id)

        try:
            await ctx.guild.ban(user, reason=reason, delete_message_days=0)
            action_result = True
        except Forbidden:
            action_result = False

        infraction_expiration = format_infraction(infraction["expires_at"])

        self.schedule_task(ctx.bot.loop, infraction["id"], infraction)

        dm_result = ":incoming_envelope: " if notified else ""
        action = f"{dm_result}:ok_hand: banned {user.mention} until {infraction_expiration}"
        await ctx.send(f"{action}.")

        dm_status = "Sent" if notified else "**Failed**"
        log_content = None if all((notified, action_result)) else ctx.author.mention
        title = "Member temporarily banned"
        if not action_result:
            title += " (Failed)"

        await self.mod_log.send_log_message(
            icon_url=Icons.user_ban,
            colour=Colour(Colours.soft_red),
            thumbnail=user.avatar_url_as(static_format="png"),
            title=title,
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                DM: {dm_status}
                Reason: {reason}
                Expires: {infraction_expiration}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    # endregion
    # region: Permanent shadow infractions

    @with_role(*MODERATION_ROLES)
    @command(hidden=True)
    async def note(self, ctx: Context, user: UserConverter, *, reason: str = None) -> None:
        """
        Create a private infraction note in the database for a user with the provided reason.

        This does not send the user a notification
        """
        infraction = await post_infraction(ctx, user, type="note", reason=reason, hidden=True)
        if infraction is None:
            return

        await ctx.send(f":ok_hand: note added for {user.mention}.")

        await self.mod_log.send_log_message(
            icon_url=Icons.user_warn,
            colour=Colour(Colours.soft_red),
            title="Member note added",
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                Reason: {reason}
            """),
            footer=f"ID {infraction['id']}"
        )

    @with_role(*MODERATION_ROLES)
    @command(hidden=True, aliases=['shadowkick', 'skick'])
    @respect_role_hierarchy()
    async def shadow_kick(self, ctx: Context, user: Member, *, reason: str = None) -> None:
        """
        Kick a user for the provided reason.

        This does not send the user a notification.
        """
        infraction = await post_infraction(ctx, user, type="kick", reason=reason, hidden=True)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_remove, user.id)

        try:
            await user.kick(reason=reason)
            action_result = True
        except Forbidden:
            action_result = False

        await ctx.send(f":ok_hand: kicked {user.mention}.")

        title = "Member shadow kicked"
        if action_result:
            log_content = None
        else:
            log_content = ctx.author.mention
            title += " (Failed)"

        await self.mod_log.send_log_message(
            icon_url=Icons.sign_out,
            colour=Colour(Colours.soft_red),
            title=title,
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                Reason: {reason}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    @with_role(*MODERATION_ROLES)
    @command(hidden=True, aliases=['shadowban', 'sban'])
    @respect_role_hierarchy()
    async def shadow_ban(self, ctx: Context, user: UserConverter, *, reason: str = None) -> None:
        """
        Create a permanent ban infraction for a user with the provided reason.

        This does not send the user a notification.
        """
        if await already_has_active_infraction(ctx=ctx, user=user, type="ban"):
            return

        infraction = await post_infraction(ctx, user, type="ban", reason=reason, hidden=True)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_ban, user.id)
        self.mod_log.ignore(Event.member_remove, user.id)

        try:
            await ctx.guild.ban(user, reason=reason, delete_message_days=0)
            action_result = True
        except Forbidden:
            action_result = False

        await ctx.send(f":ok_hand: permanently banned {user.mention}.")

        title = "Member permanently banned"
        if action_result:
            log_content = None
        else:
            log_content = ctx.author.mention
            title += " (Failed)"

        await self.mod_log.send_log_message(
            icon_url=Icons.user_ban,
            colour=Colour(Colours.soft_red),
            title=title,
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                Reason: {reason}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    # endregion
    # region: Temporary shadow infractions

    @with_role(*MODERATION_ROLES)
    @command(hidden=True, aliases=["shadowtempmute, stempmute", "shadowmute", "smute"])
    async def shadow_tempmute(
        self, ctx: Context, user: Member, duration: Duration, *, reason: str = None
    ) -> None:
        """
        Create a temporary mute infraction for a user with the provided reason.

        Duration strings are parsed per: http://strftime.org/

        This does not send the user a notification.
        """
        expiration = duration

        if await already_has_active_infraction(ctx=ctx, user=user, type="mute"):
            return

        infraction = await post_infraction(ctx, user, type="mute", reason=reason, expires_at=expiration, hidden=True)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_update, user.id)
        await user.add_roles(self._muted_role, reason=reason)

        infraction_expiration = format_infraction(infraction["expires_at"])
        self.schedule_task(ctx.bot.loop, infraction["id"], infraction)
        await ctx.send(f":ok_hand: muted {user.mention} until {infraction_expiration}.")

        await self.mod_log.send_log_message(
            icon_url=Icons.user_mute,
            colour=Colour(Colours.soft_red),
            title="Member temporarily muted",
            thumbnail=user.avatar_url_as(static_format="png"),
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                Reason: {reason}
                Expires: {infraction_expiration}
            """),
            footer=f"ID {infraction['id']}"
        )

    @with_role(*MODERATION_ROLES)
    @command(hidden=True, aliases=["shadowtempban, stempban"])
    @respect_role_hierarchy()
    async def shadow_tempban(
        self, ctx: Context, user: UserConverter, duration: Duration, *, reason: str = None
    ) -> None:
        """
        Create a temporary ban infraction for a user with the provided reason.

        Duration strings are parsed per: http://strftime.org/

        This does not send the user a notification.
        """
        expiration = duration

        if await already_has_active_infraction(ctx=ctx, user=user, type="ban"):
            return

        infraction = await post_infraction(ctx, user, type="ban", reason=reason, expires_at=expiration, hidden=True)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_ban, user.id)
        self.mod_log.ignore(Event.member_remove, user.id)

        try:
            await ctx.guild.ban(user, reason=reason, delete_message_days=0)
            action_result = True
        except Forbidden:
            action_result = False

        infraction_expiration = format_infraction(infraction["expires_at"])
        self.schedule_task(ctx.bot.loop, infraction["id"], infraction)
        await ctx.send(f":ok_hand: banned {user.mention} until {infraction_expiration}.")

        title = "Member temporarily banned"
        if action_result:
            log_content = None
        else:
            log_content = ctx.author.mention
            title += " (Failed)"

        # Send a log message to the mod log
        await self.mod_log.send_log_message(
            icon_url=Icons.user_ban,
            colour=Colour(Colours.soft_red),
            thumbnail=user.avatar_url_as(static_format="png"),
            title=title,
            text=textwrap.dedent(f"""
                Member: {user.mention} (`{user.id}`)
                Actor: {ctx.message.author}
                Reason: {reason}
                Expires: {infraction_expiration}
            """),
            content=log_content,
            footer=f"ID {infraction['id']}"
        )

    # endregion
    # region: Remove infractions (un- commands)

    @with_role(*MODERATION_ROLES)
    @command()
    async def unmute(self, ctx: Context, user: UserConverter) -> None:
        """Deactivates the active mute infraction for a user."""
        try:
            # check the current active infraction
            response = await self.bot.api_client.get(
                'bot/infractions',
                params={
                    'active': 'true',
                    'type': 'mute',
                    'user__id': user.id
                }
            )
            if len(response) > 1:
                log.warning("Found more than one active mute infraction for user `%d`", user.id)

            if not response:
                # no active infraction
                await ctx.send(
                    f":x: There is no active mute infraction for user {user.mention}."
                )
                return

            for infraction in response:
                await self._deactivate_infraction(infraction)
                if infraction["expires_at"] is not None:
                    self.cancel_expiration(infraction["id"])

            notified = await self.notify_pardon(
                user=user,
                title="You have been unmuted.",
                content="You may now send messages in the server.",
                icon_url=Icons.user_unmute
            )

            if notified:
                dm_status = "Sent"
                dm_emoji = ":incoming_envelope: "
                log_content = None
            else:
                dm_status = "**Failed**"
                dm_emoji = ""
                log_content = ctx.author.mention

            await ctx.send(f"{dm_emoji}:ok_hand: Un-muted {user.mention}.")

            embed_text = textwrap.dedent(
                f"""
                    Member: {user.mention} (`{user.id}`)
                    Actor: {ctx.message.author}
                    DM: {dm_status}
                """
            )

            if len(response) > 1:
                footer = f"Infraction IDs: {', '.join(str(infr['id']) for infr in response)}"
                title = "Member unmuted"
                embed_text += "Note: User had multiple **active** mute infractions in the database."
            else:
                infraction = response[0]
                footer = f"Infraction ID: {infraction['id']}"
                title = "Member unmuted"

            # Send a log message to the mod log
            await self.mod_log.send_log_message(
                icon_url=Icons.user_unmute,
                colour=Colour(Colours.soft_green),
                title=title,
                thumbnail=user.avatar_url_as(static_format="png"),
                text=embed_text,
                footer=footer,
                content=log_content
            )
        except Exception:
            log.exception("There was an error removing an infraction.")
            await ctx.send(":x: There was an error removing the infraction.")

    @with_role(*MODERATION_ROLES)
    @command()
    async def unban(self, ctx: Context, user: UserConverter) -> None:
        """Deactivates the active ban infraction for a user."""
        try:
            # check the current active infraction
            response = await self.bot.api_client.get(
                'bot/infractions',
                params={
                    'active': 'true',
                    'type': 'ban',
                    'user__id': str(user.id)
                }
            )
            if len(response) > 1:
                log.warning(
                    "More than one active ban infraction found for user `%d`.",
                    user.id
                )

            if not response:
                # no active infraction
                await ctx.send(
                    f":x: There is no active ban infraction for user {user.mention}."
                )
                return

            for infraction in response:
                await self._deactivate_infraction(infraction)
                if infraction["expires_at"] is not None:
                    self.cancel_expiration(infraction["id"])

            embed_text = textwrap.dedent(
                f"""
                    Member: {user.mention} (`{user.id}`)
                    Actor: {ctx.message.author}
                """
            )

            if len(response) > 1:
                footer = f"Infraction IDs: {', '.join(str(infr['id']) for infr in response)}"
                embed_text += "Note: User had multiple **active** ban infractions in the database."
            else:
                infraction = response[0]
                footer = f"Infraction ID: {infraction['id']}"

            await ctx.send(f":ok_hand: Un-banned {user.mention}.")

            # Send a log message to the mod log
            await self.mod_log.send_log_message(
                icon_url=Icons.user_unban,
                colour=Colour(Colours.soft_green),
                title="Member unbanned",
                thumbnail=user.avatar_url_as(static_format="png"),
                text=embed_text,
                footer=footer,
            )
        except Exception:
            log.exception("There was an error removing an infraction.")
            await ctx.send(":x: There was an error removing the infraction.")

    # endregion
    # region: Edit infraction commands

    @with_role(*MODERATION_ROLES)
    @group(name='infraction', aliases=('infr', 'infractions', 'inf'), invoke_without_command=True)
    async def infraction_group(self, ctx: Context) -> None:
        """Infraction manipulation commands."""
        await ctx.invoke(self.bot.get_command("help"), "infraction")

    @with_role(*MODERATION_ROLES)
    @infraction_group.command(name='edit')
    async def infraction_edit(
        self,
        ctx: Context,
        infraction_id: int,
        expires_at: Union[Duration, permanent_duration, None],
        *,
        reason: str = None
    ) -> None:
        """
        Edit the duration and/or the reason of an infraction.

        Durations are relative to the time of updating.
        Use "permanent" to mark the infraction as permanent.
        """
        if expires_at is None and reason is None:
            # Unlike UserInputError, the error handler will show a specified message for BadArgument
            raise BadArgument("Neither a new expiry nor a new reason was specified.")

        # Retrieve the previous infraction for its information.
        old_infraction = await self.bot.api_client.get(f'bot/infractions/{infraction_id}')

        request_data = {}
        confirm_messages = []
        log_text = ""

        if expires_at == "permanent":
            request_data['expires_at'] = None
            confirm_messages.append("marked as permanent")
        elif expires_at is not None:
            request_data['expires_at'] = expires_at.isoformat()
            confirm_messages.append(f"set to expire on {expires_at.strftime(INFRACTION_FORMAT)}")
        else:
            confirm_messages.append("expiry unchanged")

        if reason:
            request_data['reason'] = reason
            confirm_messages.append("set a new reason")
            log_text += f"""
                Previous reason: {old_infraction['reason']}
                New reason: {reason}
            """.rstrip()
        else:
            confirm_messages.append("reason unchanged")

        # Update the infraction
        new_infraction = await self.bot.api_client.patch(
            f'bot/infractions/{infraction_id}',
            json=request_data,
        )

        # Re-schedule infraction if the expiration has been updated
        if 'expires_at' in request_data:
            self.cancel_task(new_infraction['id'])
            loop = asyncio.get_event_loop()
            self.schedule_task(loop, new_infraction['id'], new_infraction)

            log_text += f"""
                Previous expiry: {old_infraction['expires_at'] or "Permanent"}
                New expiry: {new_infraction['expires_at'] or "Permanent"}
            """.rstrip()

        await ctx.send(f":ok_hand: Updated infraction: {' & '.join(confirm_messages)}")

        # Get information about the infraction's user
        user_id = new_infraction['user']
        user = ctx.guild.get_member(user_id)

        if user:
            user_text = f"{user.mention} (`{user.id}`)"
            thumbnail = user.avatar_url_as(static_format="png")
        else:
            user_text = f"`{user_id}`"
            thumbnail = None

        # The infraction's actor
        actor_id = new_infraction['actor']
        actor = ctx.guild.get_member(actor_id) or f"`{actor_id}`"

        await self.mod_log.send_log_message(
            icon_url=Icons.pencil,
            colour=Colour.blurple(),
            title="Infraction edited",
            thumbnail=thumbnail,
            text=textwrap.dedent(f"""
                Member: {user_text}
                Actor: {actor}
                Edited by: {ctx.message.author}{log_text}
            """)
        )

    # endregion
    # region: Search infractions

    @with_role(*MODERATION_ROLES)
    @infraction_group.group(name="search", invoke_without_command=True)
    async def infraction_search_group(self, ctx: Context, query: InfractionSearchQuery) -> None:
        """Searches for infractions in the database."""
        if isinstance(query, User):
            await ctx.invoke(self.search_user, query)

        else:
            await ctx.invoke(self.search_reason, query)

    @with_role(*MODERATION_ROLES)
    @infraction_search_group.command(name="user", aliases=("member", "id"))
    async def search_user(self, ctx: Context, user: Union[User, proxy_user]) -> None:
        """Search for infractions by member."""
        infraction_list = await self.bot.api_client.get(
            'bot/infractions',
            params={'user__id': str(user.id)}
        )
        embed = Embed(
            title=f"Infractions for {user} ({len(infraction_list)} total)",
            colour=Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, infraction_list)

    @with_role(*MODERATION_ROLES)
    @infraction_search_group.command(name="reason", aliases=("match", "regex", "re"))
    async def search_reason(self, ctx: Context, reason: str) -> None:
        """Search for infractions by their reason. Use Re2 for matching."""
        infraction_list = await self.bot.api_client.get(
            'bot/infractions', params={'search': reason}
        )
        embed = Embed(
            title=f"Infractions matching `{reason}` ({len(infraction_list)} total)",
            colour=Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, infraction_list)

    # endregion
    # region: Utility functions

    async def send_infraction_list(
        self,
        ctx: Context,
        embed: Embed,
        infractions: Iterable[Infraction]
    ) -> None:
        """Send a paginated embed of infractions for the specified user."""
        if not infractions:
            await ctx.send(f":warning: No infractions could be found for that query.")
            return

        lines = tuple(
            self._infraction_to_string(infraction)
            for infraction in infractions
        )

        await LinePaginator.paginate(
            lines,
            ctx=ctx,
            embed=embed,
            empty=True,
            max_lines=3,
            max_size=1000
        )

    def cancel_expiration(self, infraction_id: str) -> None:
        """Un-schedules a task set to expire a temporary infraction."""
        task = self.scheduled_tasks.get(infraction_id)
        if task is None:
            log.warning(f"Failed to unschedule {infraction_id}: no task found.")
            return
        task.cancel()
        log.debug(f"Unscheduled {infraction_id}.")
        del self.scheduled_tasks[infraction_id]

    async def _scheduled_task(self, infraction_object: Infraction) -> None:
        """
        Marks an infraction expired after the delay from time of scheduling to time of expiration.

        At the time of expiration, the infraction is marked as inactive on the website, and the
        expiration task is cancelled. The user is then notified via DM.
        """
        infraction_id = infraction_object["id"]

        # transform expiration to delay in seconds
        expiration_datetime = datetime.fromisoformat(infraction_object["expires_at"][:-1])
        await wait_until(expiration_datetime)

        log.debug(f"Marking infraction {infraction_id} as inactive (expired).")
        await self._deactivate_infraction(infraction_object)

        self.cancel_task(infraction_object["id"])

        # Notify the user that they've been unmuted.
        user_id = infraction_object["user"]
        guild = self.bot.get_guild(constants.Guild.id)
        await self.notify_pardon(
            user=guild.get_member(user_id),
            title="You have been unmuted.",
            content="You may now send messages in the server.",
            icon_url=Icons.user_unmute
        )

    async def _deactivate_infraction(self, infraction_object: Infraction) -> None:
        """
        A co-routine which marks an infraction as inactive on the website.

        This co-routine does not cancel or un-schedule an expiration task.
        """
        guild: Guild = self.bot.get_guild(constants.Guild.id)
        user_id = infraction_object["user"]
        infraction_type = infraction_object["type"]

        if infraction_type == "mute":
            member: Member = guild.get_member(user_id)
            if member:
                # remove the mute role
                self.mod_log.ignore(Event.member_update, member.id)
                await member.remove_roles(self._muted_role)
            else:
                log.warning(f"Failed to un-mute user: {user_id} (not found)")
        elif infraction_type == "ban":
            user: Object = Object(user_id)
            try:
                await guild.unban(user)
            except NotFound:
                log.info(f"Tried to unban user `{user_id}`, but Discord does not have an active ban registered.")

        await self.bot.api_client.patch(
            'bot/infractions/' + str(infraction_object['id']),
            json={"active": False}
        )

    def _infraction_to_string(self, infraction_object: Infraction) -> str:
        """Convert the infraction object to a string representation."""
        actor_id = infraction_object["actor"]
        guild: Guild = self.bot.get_guild(constants.Guild.id)
        actor = guild.get_member(actor_id)
        active = infraction_object["active"]
        user_id = infraction_object["user"]
        hidden = infraction_object["hidden"]
        created = format_infraction(infraction_object["inserted_at"])
        if infraction_object["expires_at"] is None:
            expires = "*Permanent*"
        else:
            expires = format_infraction(infraction_object["expires_at"])

        lines = textwrap.dedent(f"""
            {"**===============**" if active else "==============="}
            Status: {"__**Active**__" if active else "Inactive"}
            User: {self.bot.get_user(user_id)} (`{user_id}`)
            Type: **{infraction_object["type"]}**
            Shadow: {hidden}
            Reason: {infraction_object["reason"] or "*None*"}
            Created: {created}
            Expires: {expires}
            Actor: {actor.mention if actor else actor_id}
            ID: `{infraction_object["id"]}`
            {"**===============**" if active else "==============="}
        """)

        return lines.strip()

    async def notify_infraction(
            self,
            user: UserObject,
            infr_type: str,
            expires_at: Optional[str] = None,
            reason: Optional[str] = None
    ) -> bool:
        """
        Attempt to notify a user, via DM, of their fresh infraction.

        Returns a boolean indicator of whether the DM was successful.
        """
        expires_at = format_infraction(expires_at) if expires_at else "N/A"

        embed = Embed(
            description=textwrap.dedent(f"""
                **Type:** {infr_type}
                **Expires:** {expires_at}
                **Reason:** {reason or "No reason provided."}
                """),
            colour=Colour(Colours.soft_red)
        )

        icon_url = INFRACTION_ICONS.get(infr_type, Icons.token_removed)
        embed.set_author(name="Infraction Information", icon_url=icon_url, url=RULES_URL)
        embed.title = f"Please review our rules over at {RULES_URL}"
        embed.url = RULES_URL

        if infr_type in APPEALABLE_INFRACTIONS:
            embed.set_footer(text="To appeal this infraction, send an e-mail to appeals@pythondiscord.com")

        return await self.send_private_embed(user, embed)

    async def notify_pardon(
        self,
        user: UserObject,
        title: str,
        content: str,
        icon_url: str = Icons.user_verified
    ) -> bool:
        """
        Attempt to notify a user, via DM, of their expired infraction.

        Optionally returns a boolean indicator of whether the DM was successful.
        """
        embed = Embed(
            description=content,
            colour=Colour(Colours.soft_green)
        )

        embed.set_author(name=title, icon_url=icon_url)

        return await self.send_private_embed(user, embed)

    async def send_private_embed(self, user: UserObject, embed: Embed) -> bool:
        """
        A helper method for sending an embed to a user's DMs.

        Returns a boolean indicator of DM success.
        """
        try:
            # sometimes `user` is a `discord.Object`, so let's make it a proper user.
            user = await self.bot.fetch_user(user.id)

            await user.send(embed=embed)
            return True
        except (HTTPException, Forbidden, NotFound):
            log.debug(
                f"Infraction-related information could not be sent to user {user} ({user.id}). "
                "The user either could not be retrieved or probably disabled their DMs."
            )
            return False

    async def send_messages(
        self,
        ctx: Context,
        infraction: Infraction,
        user: UserObject,
        title: str,
        action_result: Optional[bool] = None
    ) -> str:
        """
        Send a mod log, notify the user, and return a non-empty string if notification succeeds.

        The returned string contains the emoji to prepend to the confirmation message to send to
        the actor and indicates that user was successfully notified of the infraction via DM.
        """
        infr_type = infraction["type"].capitalize()
        icon = INFRACTION_ICONS[infr_type]
        reason = infraction["reason"]
        expiry = infraction["expires_at"]

        dm_result = ""
        dm_log_text = ""
        log_content = None
        if not infraction["hidden"]:
            if await self.notify_infraction(user, infr_type, expiry, reason):
                dm_result = ":incoming_envelope: "
                dm_log_text = "\nDM: Sent"
            else:
                dm_log_text = "\nDM: **Failed**"
                log_content = ctx.author.mention

        if action_result is False:
            log_content = ctx.author.mention
            title += " (Failed)"

        expiry_log_text = f"Expires: {expiry}" if expiry else ""

        await self.mod_log.send_log_message(
            icon_url=icon,
            colour=Colour(Colours.soft_red),
            title=title,
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

        return dm_result

    # endregion

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Send a notification to the invoking context on a Union failure."""
        if isinstance(error, BadUnionArgument):
            if User in error.converters:
                await ctx.send(str(error.errors[0]))
                error.handled = True


def setup(bot: Bot) -> None:
    """Moderation cog load."""
    bot.add_cog(Moderation(bot))
    log.info("Cog loaded: Moderation")
