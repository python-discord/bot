import logging
import typing as t

import discord
from discord.ext.commands import Cog, Context, command, has_any_role

from bot import constants
from bot.bot import Bot
from bot.decorators import in_whitelist
from bot.utils.checks import InWhitelistCheckFailure

log = logging.getLogger(__name__)

# Sent via DMs once user joins the guild
ON_JOIN_MESSAGE = """
Welcome to Python Discord!

To show you what kind of community we are, we've created this video:
https://youtu.be/ZH26PuX3re0

As a new user, you have read-only access to a few select channels to give you a taste of what our server is like. \
In order to see the rest of the channels and to send messages, you first have to accept our rules.
"""

VERIFIED_MESSAGE = f"""
You are now verified!

You can find a copy of our rules for reference at <https://pythondiscord.com/pages/rules>.

Additionally, if you'd like to receive notifications for the announcements \
we post in <#{constants.Channels.announcements}>
from time to time, you can send `!subscribe` to <#{constants.Channels.bot_commands}> at any time \
to assign yourself the **Announcements** role. We'll mention this role every time we make an announcement.

If you'd like to unsubscribe from the announcement notifications, simply send `!unsubscribe` to \
<#{constants.Channels.bot_commands}>.

To introduce you to our community, we've made the following video:
https://youtu.be/ZH26PuX3re0
"""


async def safe_dm(coro: t.Coroutine) -> None:
    """
    Execute `coro` ignoring disabled DM warnings.

    The 50_0007 error code indicates that the target user does not accept DMs.
    As it turns out, this error code can appear on both 400 and 403 statuses,
    we therefore catch any Discord exception.

    If the request fails on any other error code, the exception propagates,
    and must be handled by the caller.
    """
    try:
        await coro
    except discord.HTTPException as discord_exc:
        log.trace(f"DM dispatch failed on status {discord_exc.status} with code: {discord_exc.code}")
        if discord_exc.code != 50_007:  # If any reason other than disabled DMs
            raise


class Verification(Cog):
    """
    User verification and role management.

    Statistics are collected in the 'verification.' namespace.

    Additionally, this cog offers the !subscribe and !unsubscribe commands,
    """

    def __init__(self, bot: Bot) -> None:
        """Start internal tasks."""
        self.bot = bot
        self.pending_members = set()

    # region: listeners

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Attempt to send initial direct message to each new member."""
        if member.guild.id != constants.Guild.id:
            return  # Only listen for PyDis events

        # If the user has the pending flag set, they will be using the alternate
        # gate and will not need a welcome DM with verification instructions.
        # We will send them an alternate DM once they verify with the welcome
        # video when they pass the gate.
        if member.pending:
            return

        log.trace(f"Sending on join message to new member: {member.id}")
        try:
            await safe_dm(member.send(ON_JOIN_MESSAGE))
        except discord.HTTPException:
            log.exception("DM dispatch failed on unexpected error code")

    @Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Check if we need to send a verification DM to a gated user."""
        if before.pending is True and after.pending is False:
            try:
                # If the member has not received a DM from our !accept command
                # and has gone through the alternate gating system we should send
                # our alternate welcome DM which includes info such as our welcome
                # video.
                await safe_dm(after.send(VERIFIED_MESSAGE))
            except discord.HTTPException:
                log.exception("DM dispatch failed on unexpected error code")

    # endregion
    # region: subscribe commands

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

    # endregion
    # region: miscellaneous

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Check for & ignore any InWhitelistCheckFailure."""
        if isinstance(error, InWhitelistCheckFailure):
            error.handled = True

    @command(name='verify')
    @has_any_role(*constants.MODERATION_ROLES)
    async def perform_manual_verification(self, ctx: Context, user: discord.Member) -> None:
        """Command for moderators to verify any user."""
        log.trace(f'verify command called by {ctx.author} for {user.id}.')

        if not user.pending:
            log.trace(f'{user.id} is already verified, aborting.')
            await ctx.send(f'{constants.Emojis.cross_mark} {user.mention} is already verified.')
            return

        # Adding a role automatically verifies the user, so we add and remove the Announcements role.
        temporary_role = self.bot.get_guild(constants.Guild.id).get_role(constants.Roles.announcements)
        await user.add_roles(temporary_role)
        await user.remove_roles(temporary_role)
        log.trace(f'{user.id} manually verified.')
        await ctx.send(f'{constants.Emojis.check_mark} {user.mention} is now verified.')

    # endregion


def setup(bot: Bot) -> None:
    """Load the Verification cog."""
    bot.add_cog(Verification(bot))
