import logging
from datetime import datetime, timedelta

from discord import Member
from discord.ext.commands import Bot, Context, command

from bot.constants import Roles, URLs
from bot.decorators import with_role

log = logging.getLogger(__name__)

REJECTION_MESSAGE = """
Hi, {user}!

Due to a current or pending cyberattack on our community, we have put in place some restrictions on the accounts that
may join the server. We have detected that you are using a relatively new account, so we are unable to provide access
to the server to you at this time.

Even so, thanks for your interest! We're excited that you'd like to join us, and we hope that this situation will be
resolved soon. In the meantime, please feel free to peruse the resources on our site at <https://pythondiscord.com>,
and have a nice day!
"""


class Defcon:
    """Time-sensitive server defense mechanisms"""
    days = None  # type: timedelta

    def __init__(self, bot: Bot):
        self.bot = bot
        self.days = timedelta(days=0)

    async def on_ready(self):
        pass  # TODO: Get duration

    async def on_member_join(self, member: Member):
        if self.days.days > 0:
            now = datetime.utcnow()

            if now - member.created_at < self.days:
                log.info(f"Rejecting user {member}: Account is too old and DEFCON is enabled")

                try:
                    await member.send(REJECTION_MESSAGE.format(user=member.mention))
                except Exception:
                    log.exception(f"Unable to send rejection message to user: {member}")

                await member.kick(reason="DEFCON active, user is too new")

    @with_role(Roles.admin, Roles.owner)
    @command(name="defcon.days", aliases=["defcon.days()", "defcon_days", "defcon_days()"])
    async def days_command(self, ctx: Context, days: int = None):
        if not days:
            # TODO: Sync with server
            self.days = timedelta(days=0)
            await ctx.send("DEFCON disabled.")
        else:
            # TODO: Sync with server
            self.days = timedelta(days=days)
            await ctx.send(f"DEFCON enabled; accounts must be {days} days old to join to the server")


def setup(bot: Bot):
    bot.add_cog(Defcon(bot))
    log.info("Cog loaded: Defcon")
