import logging

from discord import Message, NotFound, Object
from discord.ext.commands import Bot, Context, command

from bot.cogs.modlog import ModLog
from bot.constants import Channels, Event, Roles
from bot.decorators import in_channel, without_role

log = logging.getLogger(__name__)

WELCOME_MESSAGE = f"""
Hello! Welcome to the server, and thanks for verifying yourself!

For your records, these are the documents you accepted:

`1)` Our rules, here: <https://pythondiscord.com/about/rules>
`2)` Our privacy policy, here: <https://pythondiscord.com/about/privacy> - you can find information on how to have \
your information removed here as well.

Feel free to review them at any point!

Additionally, if you'd like to receive notifications for the announcements we post in <#{Channels.announcements}> \
from time to time, you can send `!subscribe` to <#{Channels.bot}> at any time to assign yourself the \
**Announcements** role. We'll mention this role every time we make an announcement.

If you'd like to unsubscribe from the announcement notifications, simply send `!unsubscribe` to <#{Channels.bot}>.
"""


class Verification:
    """
    User verification and role self-management
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.bot.add_check(self.block_other_commands)

    @property
    def mod_log(self) -> ModLog:
        return self.bot.get_cog("ModLog")

    async def on_message(self, message: Message):
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
    async def accept_command(self, ctx: Context, *_):  # We don't actually care about the args
        """
        Accept our rules and gain access to the rest of the server
        """

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
    async def subscribe_command(self, ctx: Context, *_):  # We don't actually care about the args
        """
        Subscribe to announcement notifications by assigning yourself the role
        """

        has_role = False

        for role in ctx.author.roles:
            if role.id == Roles.announcements:
                has_role = True
                break

        if has_role:
            return await ctx.send(
                f"{ctx.author.mention} You're already subscribed!",
            )

        log.debug(f"{ctx.author} called !subscribe. Assigning the 'Announcements' role.")
        await ctx.author.add_roles(Object(Roles.announcements), reason="Subscribed to announcements")

        log.trace(f"Deleting the message posted by {ctx.author}.")

        await ctx.send(
            f"{ctx.author.mention} Subscribed to <#{Channels.announcements}> notifications.",
        )

    @command(name='unsubscribe')
    @in_channel(Channels.bot)
    async def unsubscribe_command(self, ctx: Context, *_):  # We don't actually care about the args
        """
        Unsubscribe from announcement notifications by removing the role from yourself
        """

        has_role = False

        for role in ctx.author.roles:
            if role.id == Roles.announcements:
                has_role = True
                break

        if not has_role:
            return await ctx.send(
                f"{ctx.author.mention} You're already unsubscribed!"
            )

        log.debug(f"{ctx.author} called !unsubscribe. Removing the 'Announcements' role.")
        await ctx.author.remove_roles(Object(Roles.announcements), reason="Unsubscribed from announcements")

        log.trace(f"Deleting the message posted by {ctx.author}.")

        await ctx.send(
            f"{ctx.author.mention} Unsubscribed from <#{Channels.announcements}> notifications."
        )

    @staticmethod
    def block_other_commands(ctx: Context):
        """
        Block any command within the verification channel that is not !accept.
        """

        if ctx.channel.id == Channels.verification:
            return ctx.command.name == "accept"
        else:
            return True


def setup(bot):
    bot.add_cog(Verification(bot))
    log.info("Cog loaded: Verification")
