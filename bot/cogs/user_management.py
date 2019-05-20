import logging

from discord import Message, NotFound, Object, Member, DiscordException
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


class UserManagement:
    """
    Assigning roles to users and sending a DM when they join the server.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def mod_log(self) -> ModLog:
        return self.bot.get_cog("ModLog")

    async def on_member_join(self, member: Member):
        """
        Send a welcome DM when members join the community.
        """

        try:
            await member.send(WELCOME_MESSAGE)
        except DiscordException:
            # Catch the exception, in case they have DMs off or something
            log.exception(f"Unable to send welcome message to user {member}.")

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


def setup(bot):
    bot.add_cog(UserManagement(bot))
    log.info("Cog loaded: UserManagement")
