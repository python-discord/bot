import logging
from contextlib import suppress

from discord import Colour, Forbidden, Message, NotFound, Object
from discord.ext.commands import Cog, Context, command

from bot import constants
from bot.bot import Bot
from bot.cogs.moderation import ModLog
from bot.decorators import in_whitelist, without_role
from bot.utils.checks import InWhitelistCheckFailure, without_role_check

log = logging.getLogger(__name__)

WELCOME_MESSAGE = f"""
Hello! Welcome to the server, and thanks for verifying yourself!

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

BOT_MESSAGE_DELETE_DELAY = 10


class Verification(Cog):
    """User verification and role self-management."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
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
                colour=Colour(constants.Colours.soft_red),
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
        with suppress(NotFound):
            await ctx.message.delete()

    @command(name='accept', aliases=('verify', 'verified', 'accepted'), hidden=True)
    @without_role(constants.Roles.verified)
    @in_whitelist(channels=(constants.Channels.verification,))
    async def accept_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Accept our rules and gain access to the rest of the server."""
        log.debug(f"{ctx.author} called !accept. Assigning the 'Developer' role.")
        await ctx.author.add_roles(Object(constants.Roles.verified), reason="Accepted the rules")
        try:
            await ctx.author.send(WELCOME_MESSAGE)
        except Forbidden:
            log.info(f"Sending welcome message failed for {ctx.author}.")
        finally:
            log.trace(f"Deleting accept message by {ctx.author}.")
            with suppress(NotFound):
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
        await ctx.author.add_roles(Object(constants.Roles.announcements), reason="Subscribed to announcements")

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
        await ctx.author.remove_roles(Object(constants.Roles.announcements), reason="Unsubscribed from announcements")

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
