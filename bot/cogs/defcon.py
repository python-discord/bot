import logging
from datetime import datetime, timedelta

from discord import Colour, Embed, Member
from discord.ext.commands import Bot, Context, command

from bot.constants import Channels, Keys, Roles, URLs
from bot.decorators import with_role

log = logging.getLogger(__name__)

REJECTION_MESSAGE = """
Hi, {user} - Thanks for your interest in our server!

Due to a current (or detected) cyberattack on our community, we've limited access to the server for new accounts. Since
your account is relatively now, we're unable to provide access to the server at this time.

Even so, thanks for joining! We're very excited at the possibility of having you here, and we hope that this situation
will be resolved soon. In the meantime, please feel free to peruse the resources on our site at
<https://pythondiscord.com/>, and have a nice day!
"""


class Defcon:
    """Time-sensitive server defense mechanisms"""
    days = None  # type: timedelta
    enabled = False  # type: bool

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
                self.enabled = True
                self.days = timedelta(days=data["defcon_days"])
                log.warning(f"DEFCON enabled: {self.days.days} days")

            else:
                self.enabled = False
                self.days = timedelta(days=0)
                log.warning(f"DEFCON disabled")

    async def on_member_join(self, member: Member):
        if self.enabled and self.days.days > 0:
            now = datetime.utcnow()

            if now - member.created_at < self.days:
                log.info(f"Rejecting user {member}: Account is too old and DEFCON is enabled")

                try:
                    await member.send(REJECTION_MESSAGE.format(user=member.mention))
                except Exception:
                    log.exception(f"Unable to send rejection message to user: {member}")

                await member.kick(reason="DEFCON active, user is too new")

    @with_role(Roles.admin, Roles.owner)
    @command(name="defcon.enable", aliases=["defcon.enable()", "defcon_enable", "defcon_enable()"])
    async def enable(self, ctx: Context):
        """
        Enable DEFCON mode. Useful in a pinch, but be sure you know what you're doing!

        Currently, this just adds an account age requirement. Use bot.defcon.days(int) to set how old an account must
        be, in days.
        """

        self.enabled = True

        try:
            response = await self.bot.http_session.put(
                URLs.site_settings_api,
                headers=self.headers,
                json={"defcon_enabled": True}
            )

            await response.json()
        except Exception:
            log.exception("Unable to update DEFCON settings.")
            await ctx.send("DEFCON enabled locally, but there was a problem updating the site.")
        else:
            await ctx.send("DEFCON enabled.")

    @with_role(Roles.admin, Roles.owner)
    @command(name="defcon.disable", aliases=["defcon.disable()", "defcon_disable", "defcon_disable()"])
    async def disable(self, ctx: Context):
        """
        Disable DEFCON mode. Useful in a pinch, but be sure you know what you're doing!
        """

        self.enabled = False

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

    @with_role(Roles.admin, Roles.owner)
    @command(name="defcon", aliases=["defcon()", "defcon.status", "defcon.status()"])
    async def defcon(self, ctx: Context):
        """
        Check the current status of DEFCON mode.
        """

        embed = Embed(colour=Colour.blurple(), title="DEFCON Status")
        embed.add_field(name="Enabled", value=str(self.enabled), inline=True)
        embed.add_field(name="Days", value=str(self.days.days), inline=True)

        await ctx.send(embed=embed)

    @with_role(Roles.admin, Roles.owner)
    @command(name="defcon.days", aliases=["defcon.days()", "defcon_days", "defcon_days()"])
    async def days_command(self, ctx: Context, days: int):
        """
        Set how old an account must be to join the server, in days, with DEFCON mode enabled.
        """

        self.days = timedelta(days=days)

        try:
            response = await self.bot.http_session.put(
                URLs.site_settings_api,
                headers=self.headers,
                json={"defcon_days": days}
            )

            await response.json()
        except Exception:
            log.exception("Unable to update DEFCON settings.")
            await ctx.send(
                f"DEFCON days updated; accounts must be {days} days old to join to the server "
                f"- but there was a problem updating the site."
            )
        else:
            await ctx.send(f"DEFCON days updated; accounts must be {days} days old to join to the server")


def setup(bot: Bot):
    bot.add_cog(Defcon(bot))
    log.info("Cog loaded: Defcon")
