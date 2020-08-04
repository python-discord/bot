import asyncio
import logging
import typing as t
from contextlib import suppress
from datetime import datetime, timedelta

import discord
from discord.ext.commands import Cog, Context, command

from bot import constants
from bot.bot import Bot
from bot.cogs.moderation import ModLog
from bot.decorators import in_whitelist, without_role
from bot.utils.checks import InWhitelistCheckFailure, without_role_check

log = logging.getLogger(__name__)

ON_JOIN_MESSAGE = f"""
Hello! Welcome to Python Discord!

In order to send messages, you first have to accept our rules. To do so, please visit \
<#{constants.Channels.verification}>. Thank you!
"""

VERIFIED_MESSAGE = f"""
Thanks for verifying yourself!

For your records, these are the documents you accepted:

`1)` Our rules, here: <https://pythondiscord.com/pages/rules>
`2)` Our privacy policy, here: <https://pythondiscord.com/pages/privacy> - you can find information on how to have \
your information removed here as well.

Feel free to review them at any point!

Additionally, if you'd like to receive notifications for the announcements \
we post in <#{constants.Channels.announcements}>
from time to time, you can send `!subscribe` to <#{constants.Channels.bot_commands}> at any time \
to assign yourself the **Announcements** role. We'll mention this role every time we make an announcement.

If you'd like to unsubscribe from the announcement notifications, simply send `!unsubscribe` to \
<#{constants.Channels.bot_commands}>.
"""

UNVERIFIED_AFTER = 3  # Amount of days after which non-Developers receive the @Unverified role
KICKED_AFTER = 30  # Amount of days after which non-Developers get kicked from the guild

BOT_MESSAGE_DELETE_DELAY = 10


class Verification(Cog):
    """User verification and role self-management."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def _kick_members(self, members: t.Set[discord.Member]) -> int:
        """Kick `members` from the PyDis guild."""
        ...

    async def _give_role(self, members: t.Set[discord.Member], role: discord.Role) -> int:
        """Give `role` to all `members`."""
        ...

    async def check_users(self) -> None:
        """
        Periodically check in on the verification status of PyDis members.

        This coroutine performs two actions:
            * Find members who have not verified for `UNVERIFIED_AFTER` and give them the @Unverified role
            * Find members who have not verified for `KICKED_AFTER` and kick them from the guild

        Within the body of this coroutine, we only select the members for each action. The work is then
        delegated to `_kick_members` and `_give_role`. After each run, a report is sent via modlog.
        """
        await self.bot.wait_until_guild_available()  # Ensure cache is ready
        pydis = self.bot.get_guild(constants.Guild.id)

        unverified = pydis.get_role(constants.Roles.unverified)
        current_dt = datetime.utcnow()  # Discord timestamps are UTC

        # Users to be given the @Unverified role, and those to be kicked, these should be entirely disjoint
        for_role, for_kick = set(), set()

        log.debug("Checking verification status of guild members")
        for member in pydis.members:

            # Skip all bots and users for which we don't know their join date
            # This should be extremely rare, but can happen according to `joined_at` docs
            if member.bot or member.joined_at is None:
                continue

            # Now we check roles to determine whether this user has already verified
            unverified_roles = {unverified, pydis.default_role}  # Verified users have at least one more role
            if set(member.roles) - unverified_roles:
                continue

            # At this point, we know that `member` is an unverified user, and we will decide what
            # to do with them based on time passed since their join date
            since_join = current_dt - member.joined_at

            if since_join > timedelta(days=KICKED_AFTER):
                for_kick.add(member)  # User should be removed from the guild

            elif since_join > timedelta(days=UNVERIFIED_AFTER) and unverified not in member.roles:
                for_role.add(member)  # User should be given the @Unverified role

        log.debug(f"{len(for_role)} users will be given the {unverified} role, {len(for_kick)} users will be kicked")
        n_kicks = await self._kick_members(for_kick)
        n_roles = await self._give_role(for_role, unverified)

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Attempt to send initial direct message to each new member."""
        if member.guild.id != constants.Guild.id:
            return  # Only listen for PyDis events

        log.trace(f"Sending on join message to new member: {member.id}")
        with suppress(discord.Forbidden):
            await member.send(ON_JOIN_MESSAGE)

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Check new message event for messages to the checkpoint channel & process."""
        if message.channel.id != constants.Channels.verification:
            return  # Only listen for #checkpoint messages

        if message.author.bot:
            # They're a bot, delete their message after the delay.
            await message.delete(delay=BOT_MESSAGE_DELETE_DELAY)
            return

        # if a user mentions a role or guild member
        # alert the mods in mod-alerts channel
        if message.mentions or message.role_mentions:
            log.debug(
                f"{message.author} mentioned one or more users "
                f"and/or roles in {message.channel.name}"
            )

            embed_text = (
                f"{message.author.mention} sent a message in "
                f"{message.channel.mention} that contained user and/or role mentions."
                f"\n\n**Original message:**\n>>> {message.content}"
            )

            # Send pretty mod log embed to mod-alerts
            await self.mod_log.send_log_message(
                icon_url=constants.Icons.filtering,
                colour=discord.Colour(constants.Colours.soft_red),
                title=f"User/Role mentioned in {message.channel.name}",
                text=embed_text,
                thumbnail=message.author.avatar_url_as(static_format="png"),
                channel_id=constants.Channels.mod_alerts,
            )

        ctx: Context = await self.bot.get_context(message)
        if ctx.command is not None and ctx.command.name == "accept":
            return

        if any(r.id == constants.Roles.verified for r in ctx.author.roles):
            log.info(
                f"{ctx.author} posted '{ctx.message.content}' "
                "in the verification channel, but is already verified."
            )
            return

        log.debug(
            f"{ctx.author} posted '{ctx.message.content}' in the verification "
            "channel. We are providing instructions how to verify."
        )
        await ctx.send(
            f"{ctx.author.mention} Please type `!accept` to verify that you accept our rules, "
            f"and gain access to the rest of the server.",
            delete_after=20
        )

        log.trace(f"Deleting the message posted by {ctx.author}")
        with suppress(discord.NotFound):
            await ctx.message.delete()

    @command(name='accept', aliases=('verify', 'verified', 'accepted'), hidden=True)
    @without_role(constants.Roles.verified)
    @in_whitelist(channels=(constants.Channels.verification,))
    async def accept_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Accept our rules and gain access to the rest of the server."""
        log.debug(f"{ctx.author} called !accept. Assigning the 'Developer' role.")
        await ctx.author.add_roles(discord.Object(constants.Roles.verified), reason="Accepted the rules")
        try:
            await ctx.author.send(VERIFIED_MESSAGE)
        except discord.Forbidden:
            log.info(f"Sending welcome message failed for {ctx.author}.")
        finally:
            log.trace(f"Deleting accept message by {ctx.author}.")
            with suppress(discord.NotFound):
                self.mod_log.ignore(constants.Event.message_delete, ctx.message.id)
                await ctx.message.delete()

    @command(name='subscribe')
    @in_whitelist(channels=(constants.Channels.bot_commands,))
    async def subscribe_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Subscribe to announcement notifications by assigning yourself the role."""
        has_role = False

        for role in ctx.author.roles:
            if role.id == constants.Roles.announcements:
                has_role = True
                break

        if has_role:
            await ctx.send(f"{ctx.author.mention} You're already subscribed!")
            return

        log.debug(f"{ctx.author} called !subscribe. Assigning the 'Announcements' role.")
        await ctx.author.add_roles(discord.Object(constants.Roles.announcements), reason="Subscribed to announcements")

        log.trace(f"Deleting the message posted by {ctx.author}.")

        await ctx.send(
            f"{ctx.author.mention} Subscribed to <#{constants.Channels.announcements}> notifications.",
        )

    @command(name='unsubscribe')
    @in_whitelist(channels=(constants.Channels.bot_commands,))
    async def unsubscribe_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Unsubscribe from announcement notifications by removing the role from yourself."""
        has_role = False

        for role in ctx.author.roles:
            if role.id == constants.Roles.announcements:
                has_role = True
                break

        if not has_role:
            await ctx.send(f"{ctx.author.mention} You're already unsubscribed!")
            return

        log.debug(f"{ctx.author} called !unsubscribe. Removing the 'Announcements' role.")
        await ctx.author.remove_roles(
            discord.Object(constants.Roles.announcements), reason="Unsubscribed from announcements"
        )

        log.trace(f"Deleting the message posted by {ctx.author}.")

        await ctx.send(
            f"{ctx.author.mention} Unsubscribed from <#{constants.Channels.announcements}> notifications."
        )

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Check for & ignore any InWhitelistCheckFailure."""
        if isinstance(error, InWhitelistCheckFailure):
            error.handled = True

    @staticmethod
    def bot_check(ctx: Context) -> bool:
        """Block any command within the verification channel that is not !accept."""
        if ctx.channel.id == constants.Channels.verification and without_role_check(ctx, *constants.MODERATION_ROLES):
            return ctx.command.name == "accept"
        else:
            return True


def setup(bot: Bot) -> None:
    """Load the Verification cog."""
    bot.add_cog(Verification(bot))
