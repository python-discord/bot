import logging

from discord import DiscordException, Member, Object
from discord.ext.commands import Bot, Context, command

from bot.constants import Channels, Roles
from bot.decorators import in_channel

log = logging.getLogger(__name__)

WELCOME_MESSAGE = f"""
Welcome to Python Discord!

If you'd like to be a member of this community, please have a look at the following documents:
Our rules: <https://pythondiscord.com/about/rules>
Our privacy policy: <https://pythondiscord.com/about/privacy>

If you'd like to receive notifications for the announcements we post in <#{Channels.announcements}> \
from time to time, you can send `!subscribe` to <#{Channels.bot}> at any time to assign yourself the \
**Announcements** role. We'll mention this role every time we make an important announcement.

If you'd like to unsubscribe from the announcement notifications, simply send `!unsubscribe` to <#{Channels.bot}>.

Thank you for joining our community, and we hope you enjoy your time here.
"""


class UserManagement:
    """
    Assigning roles to users and sending a DM when they join the server.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    async def on_member_join(member: Member):
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

        has_role = any(r.id == Roles.announcements for r in ctx.author.roles)
        if has_role:
            return await ctx.send(f"{ctx.author.mention} You're already subscribed!")

        log.debug(f"{ctx.author} called !subscribe. Assigning the 'Announcements' role.")
        await ctx.author.add_roles(Object(Roles.announcements), reason="Subscribed to announcements")

        await ctx.send(
            f"{ctx.author.mention} Subscribed to <#{Channels.announcements}> notifications.",
        )

    @command(name='unsubscribe')
    @in_channel(Channels.bot)
    async def unsubscribe_command(self, ctx: Context, *_):  # We don't actually care about the args
        """
        Unsubscribe from announcement notifications by removing the role from yourself
        """

        has_role = any(r.id == Roles.announcements for r in ctx.author.roles)
        if not has_role:
            return await ctx.send(f"{ctx.author.mention} You're already unsubscribed!")

        log.debug(f"{ctx.author} called !unsubscribe. Removing the 'Announcements' role.")
        await ctx.author.remove_roles(Object(Roles.announcements), reason="Unsubscribed from announcements")

        await ctx.send(f"{ctx.author.mention} Unsubscribed from <#{Channels.announcements}> notifications.")


def setup(bot):
    bot.add_cog(UserManagement(bot))
    log.info("Cog loaded: UserManagement")
