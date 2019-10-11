import logging
from datetime import datetime

from discord import Message, NotFound, Object
from discord.ext import tasks
from discord.ext.commands import Bot, Cog, Context, command

from bot.cogs.modlog import ModLog
from bot.constants import Channels, Event, Roles
from bot.decorators import InChannelCheckFailure, in_channel, without_role

log = logging.getLogger(__name__)

WELCOME_MESSAGE = f"""
Hello! Welcome to the server, and thanks for verifying yourself!

For your records, these are the documents you accepted:

`1)` Our rules, here: <https://pythondiscord.com/pages/rules>
`2)` Our privacy policy, here: <https://pythondiscord.com/pages/privacy> - you can find information on how to have \
your information removed here as well.

Feel free to review them at any point!

Additionally, if you'd like to receive notifications for the announcements we post in <#{Channels.announcements}> \
from time to time, you can send `!subscribe` to <#{Channels.bot}> at any time to assign yourself the \
**Announcements** role. We'll mention this role every time we make an announcement.

If you'd like to unsubscribe from the announcement notifications, simply send `!unsubscribe` to <#{Channels.bot}>.
"""

PERIODIC_PING = (
    "@everyone To verify that you have read our rules, please type `!accept`."
    f" Ping <@&{Roles.admin}> if you encounter any problems during the verification process."
)


class Verification(Cog):
    """User verification and role self-management."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.periodic_ping.start()

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Check new message event for messages to the checkpoint channel & process."""
        if message.author.bot:
            return  # They're a bot, ignore

        ctx = await self.bot.get_context(message)  # type: Context

        if ctx.command is not None and ctx.command.name == "accept":
            return  # They used the accept command

        if ctx.channel.id == Channels.verification:  # We're in the verification channel
            for role in ctx.author.roles:
                if role.id == Roles.verified:
                    log.warning(f"{ctx.author} posted '{ctx.message.content}' "
                                "in the verification channel, but is already verified.")
                    return  # They're already verified

            log.debug(f"{ctx.author} posted '{ctx.message.content}' in the verification "
                      "channel. We are providing instructions how to verify.")
            await ctx.send(
                f"{ctx.author.mention} Please type `!accept` to verify that you accept our rules, "
                f"and gain access to the rest of the server.",
                delete_after=20
            )

            log.trace(f"Deleting the message posted by {ctx.author}")

            try:
                await ctx.message.delete()
            except NotFound:
                log.trace("No message found, it must have been deleted by another bot.")

    @command(name='accept', aliases=('verify', 'verified', 'accepted'), hidden=True)
    @without_role(Roles.verified)
    @in_channel(Channels.verification)
    async def accept_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Accept our rules and gain access to the rest of the server."""
        log.debug(f"{ctx.author} called !accept. Assigning the 'Developer' role.")
        await ctx.author.add_roles(Object(Roles.verified), reason="Accepted the rules")
        try:
            await ctx.author.send(WELCOME_MESSAGE)
        except Exception:
            # Catch the exception, in case they have DMs off or something
            log.exception(f"Unable to send welcome message to user {ctx.author}.")

        log.trace(f"Deleting the message posted by {ctx.author}.")

        try:
            self.mod_log.ignore(Event.message_delete, ctx.message.id)
            await ctx.message.delete()
        except NotFound:
            log.trace("No message found, it must have been deleted by another bot.")

    @command(name='subscribe')
    @in_channel(Channels.bot)
    async def subscribe_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Subscribe to announcement notifications by assigning yourself the role."""
        has_role = False

        for role in ctx.author.roles:
            if role.id == Roles.announcements:
                has_role = True
                break

        if has_role:
            await ctx.send(f"{ctx.author.mention} You're already subscribed!")
            return

        log.debug(f"{ctx.author} called !subscribe. Assigning the 'Announcements' role.")
        await ctx.author.add_roles(Object(Roles.announcements), reason="Subscribed to announcements")

        log.trace(f"Deleting the message posted by {ctx.author}.")

        await ctx.send(
            f"{ctx.author.mention} Subscribed to <#{Channels.announcements}> notifications.",
        )

    @command(name='unsubscribe')
    @in_channel(Channels.bot)
    async def unsubscribe_command(self, ctx: Context, *_) -> None:  # We don't actually care about the args
        """Unsubscribe from announcement notifications by removing the role from yourself."""
        has_role = False

        for role in ctx.author.roles:
            if role.id == Roles.announcements:
                has_role = True
                break

        if not has_role:
            await ctx.send(f"{ctx.author.mention} You're already unsubscribed!")
            return

        log.debug(f"{ctx.author} called !unsubscribe. Removing the 'Announcements' role.")
        await ctx.author.remove_roles(Object(Roles.announcements), reason="Unsubscribed from announcements")

        log.trace(f"Deleting the message posted by {ctx.author}.")

        await ctx.send(
            f"{ctx.author.mention} Unsubscribed from <#{Channels.announcements}> notifications."
        )

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Check for & ignore any InChannelCheckFailure."""
        if isinstance(error, InChannelCheckFailure):
            error.handled = True

    @staticmethod
    def bot_check(ctx: Context) -> bool:
        """Block any command within the verification channel that is not !accept."""
        if ctx.channel.id == Channels.verification:
            return ctx.command.name == "accept"
        else:
            return True

    @tasks.loop(hours=12)
    async def periodic_ping(self) -> None:
        """Post a recap message every week with an @everyone."""
        messages = self.bot.get_channel(Channels.verification).history(limit=10)  # check lasts messages
        need_to_post = True  # if the bot has to post a new message in the channel
        async for message in messages:
            if message.content == PERIODIC_PING:  # to be sure to measure timelaps between two identical messages
                delta = datetime.utcnow() - message.created_at  # time since last periodic ping
                if delta.days >= 7:  # if the message is older than a week
                    await message.delete()
                else:
                    need_to_post = False
                break
        if need_to_post:  # if the bot did not posted yet
            await self.bot.get_channel(Channels.verification).send(PERIODIC_PING)

    @periodic_ping.before_loop
    async def before_ping(self) -> None:
        """Only start the loop when the bot is ready."""
        await self.bot.wait_until_ready()

    def cog_unload(self) -> None:
        """Cancel the periodic ping task when the cog is unloaded."""
        self.periodic_ping.cancel()


def setup(bot: Bot) -> None:
    """Verification cog load."""
    bot.add_cog(Verification(bot))
    log.info("Cog loaded: Verification")
