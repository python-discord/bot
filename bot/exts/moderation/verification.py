import typing as t

import discord
from discord.ext.commands import Cog, Context, command, has_any_role

from bot import constants
from bot.bot import Bot
from bot.log import get_logger

log = get_logger(__name__)

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
from time to time, you can send `{constants.Bot.prefix}subscribe` to <#{constants.Channels.bot_commands}> at any time \
to assign yourself the **Announcements** role. We'll mention this role every time we make an announcement.

If you'd like to unsubscribe from the announcement notifications, simply send `{constants.Bot.prefix}subscribe` to \
<#{constants.Channels.bot_commands}> and click the role again!.

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
    User verification.

    Statistics are collected in the 'verification.' namespace.
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
    # region: miscellaneous

    @command(name="verify")
    @has_any_role(*constants.MODERATION_ROLES)
    async def perform_manual_verification(self, ctx: Context, user: discord.Member) -> None:
        """Command for moderators to verify any user."""
        log.trace(f"verify command called by {ctx.author} for {user.id}.")

        if not user.pending:
            log.trace(f"{user.id} is already verified, aborting.")
            await ctx.send(f"{constants.Emojis.cross_mark} {user.mention} is already verified.")
            return

        # Adding a role automatically verifies the user, so we add and remove the Announcements role.
        temporary_role = self.bot.get_guild(constants.Guild.id).get_role(constants.Roles.announcements)
        await user.add_roles(temporary_role)
        await user.remove_roles(temporary_role)
        log.trace(f"{user.id} manually verified.")
        await ctx.send(f"{constants.Emojis.check_mark} {user.mention} is now verified.")

    # endregion


async def setup(bot: Bot) -> None:
    """Load the Verification cog."""
    await bot.add_cog(Verification(bot))
