import logging

from discord import User
from discord.ext.commands import Bot, command

from bot.constants import Keys, Roles, URLs
from bot.decorators import with_role

log = logging.getLogger(__name__)


class Moderation:
    """
    Rowboat replacement moderation tools.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.warn")
    async def warn(self, ctx, user: User, *, reason: str):
        """
        Create a warning infraction in the database for a user.
        :param user: accepts user mention, ID, etc.
        :param reason: the reason for the warning.
        """

        try:
            response = await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "warning",
                    "reason": reason,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except Exception:
            # Same as defcon. Probably not the best but may work for now.
            log.exception("There was an error adding an infraction.")
            await ctx.send("There was an error updating the site.")
            return

        await ctx.send("Warning added.")

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.ban")
    async def ban(self, ctx, user: User, reason: str, duration: str = None):
        """
        Create a banning infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param reason: Wrap in quotes to make reason larger than one word.
        :param duration: Accepts #d, #h, #m, and #s.
        """

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.mute")
    async def mute(self, ctx, user: User, reason: str, duration: str = None):
        """
        Create a muting infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param reason: Wrap in quotes to make reason larger than one word.
        :param duration: Accepts #d, #h, #m, and #s.
        """


def setup(bot):
    bot.add_cog(Moderation(bot))
    # Here we'll need to call a command I haven't made yet
    # It'll check the expiry queue and automatically set up tasks for
    # temporary bans, mutes, etc.
    log.info("Cog loaded: Moderation")
