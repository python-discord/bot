import logging

from discord import Guild, Member, User
from discord.ext.commands import Bot, Context, command

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
    async def warn(self, ctx: Context, user: User, reason: str = None):
        """
        Create a warning infraction in the database for a user.
        :param user: accepts user mention, ID, etc.
        :param reason: the reason for the warning. Wrap in string quotes for multiple words.
        """

        try:
            await self.bot.http_session.post(
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
            log.exception("There was an error adding an infraction.")
            await ctx.send("There was an error adding the infraction.")
            return

        if reason is None:
            result_message = f":ok_hand: warned {user.mention}."
        else:
            result_message = f":ok_hand: warned {user.mention} ({reason})."

        await ctx.send(result_message)

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.ban")
    async def ban(self, ctx: Context, user: User, reason: str = None):
        """
        Create a permanent ban infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param reason: Wrap in quotes to make reason larger than one word.
        """
        try:
            await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "ban",
                    "reason": reason,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except Exception:
            log.exception("There was an error adding an infraction.")
            await ctx.send("There was an error adding the infraction.")
            return

        guild: Guild = ctx.guild
        await guild.ban(user, reason=reason, delete_message_days=0)

        if reason is None:
            result_message = f":ok_hand: permanently banned {user.mention}."
        else:
            result_message = f":ok_hand: permanently banned {user.mention} ({reason})."

        await ctx.send(result_message)

    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    @command(name="moderation.mute")
    async def mute(self, ctx: Context, user: Member, reason: str):
        """
        Create a permanent mute infraction in the database for a user.
        :param user: Accepts user mention, ID, etc.
        :param reason: Wrap in quotes to make reason larger than one word.
        :param duration: Accepts #d, #h, #m, and #s.
        """
        try:
            await self.bot.http_session.post(
                URLs.site_infractions,
                headers=self.headers,
                json={
                    "type": "mute",
                    "reason": reason,
                    "user_id": str(user.id),
                    "actor_id": str(ctx.message.author.id)
                }
            )
        except Exception:
            log.exception("There was an error adding an infraction.")
            await ctx.send("There was an error adding the infraction.")
            return

        await user.edit(reason=reason, mute=True)

        if reason is None:
            result_message = f":ok_hand: permanently muted {user.mention}."
        else:
            result_message = f":ok_hand: permanently muted {user.mention} ({reason})."

        await ctx.send(result_message)


def setup(bot):
    bot.add_cog(Moderation(bot))
    # Here we'll need to call a command I haven't made yet
    # It'll check the expiry queue and automatically set up tasks for
    # temporary bans, mutes, etc.
    log.info("Cog loaded: Moderation")
