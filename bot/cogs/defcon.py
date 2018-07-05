import logging
from datetime import datetime, timedelta

from discord import Member
from discord.ext.commands import Bot, Context, command

from bot.constants import Roles, URLs, Keys, Channels
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
        self.headers = {"X-API-KEY": Keys.site_api}

    async def on_ready(self):
        try:
            response = await self.bot.http_session.get(
                URLs.site_settings_api,
                headers=self.headers,
                params={"keys": "defcon_enabled,defcon_days"}
            )

            data = await response.json()

        except Exception:  # Yikes!
            log.exception("Unable to get DEFCON settings!")
            await self.bot.get_channel(Channels.devlog).send(
                f"<@&{Roles.admin}> **WARNING**: Unable to get DEFCON settings!"
            )

        else:
            if data["defcon_enabled"]:
                self.days = timedelta(days=data["defcon_days"])
                log.warning(f"DEFCON enabled: {self.days.days} days")

            else:
                self.days = timedelta(days=0)
                log.warning(f"DEFCON disabled")

    # async def on_member_join(self, member: Member):
    #     if self.days.days > 0:
    #         now = datetime.utcnow()
    #
    #         if now - member.created_at < self.days:
    #             log.info(f"Rejecting user {member}: Account is too old and DEFCON is enabled")
    #
    #             try:
    #                 await member.send(REJECTION_MESSAGE.format(user=member.mention))
    #             except Exception:
    #                 log.exception(f"Unable to send rejection message to user: {member}")
    #
    #             await member.kick(reason="DEFCON active, user is too new")

    @with_role(Roles.admin, Roles.owner)
    @command(name="defcon.days", aliases=["defcon.days()", "defcon_days", "defcon_days()"])
    async def days_command(self, ctx: Context, days: int = None):
        if not days:
            self.days = timedelta(days=0)

            try:
                response = await self.bot.http_session.put(
                    URLs.site_settings_api,
                    headers=self.headers,
                    json={"defcon_enabled": False}
                )

                await response.json()
            except Exception:
                log.exception("Unable to update DEFCON settings.")
                await ctx.send("DEFCON disabled locally, but there was a problem updating the site.")
            else:
                await ctx.send("DEFCON disabled.")
        else:
            # TODO: Sync with server
            self.days = timedelta(days=days)

            try:
                response = await self.bot.http_session.put(
                    URLs.site_settings_api,
                    headers=self.headers,
                    json={"defcon_enabled": True, "defcon_days": days}
                )

                await response.json()
            except Exception:
                log.exception("Unable to update DEFCON settings.")
                await ctx.send(
                    f"DEFCON enabled locally; accounts must be {days} days old to join to the server "
                    f"- but there was a problem updating the site."
                )
            else:
                await ctx.send(f"DEFCON enabled; accounts must be {days} days old to join to the server")


def setup(bot: Bot):
    bot.add_cog(Defcon(bot))
    log.info("Cog loaded: Defcon")
