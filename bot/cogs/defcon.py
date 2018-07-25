import logging
from datetime import datetime, timedelta

from discord import Colour, Embed, Member
from discord.ext.commands import Bot, Context, command

from bot.cogs.modlog import ModLog
from bot.constants import Channels, Emojis, Icons, Keys, Roles, URLs
from bot.decorators import with_role

log = logging.getLogger(__name__)

COLOUR_RED = Colour(0xcd6d6d)
COLOUR_GREEN = Colour(0x68c290)

REJECTION_MESSAGE = """
Hi, {user} - Thanks for your interest in our server!

Due to a current (or detected) cyberattack on our community, we've limited access to the server for new accounts. Since
your account is relatively new, we're unable to provide access to the server at this time.

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

    @property
    def modlog(self) -> ModLog:
        return self.bot.get_cog("ModLog")

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
                log.info(f"Rejecting user {member}: Account is too new and DEFCON is enabled")

                message_sent = False

                try:
                    await member.send(REJECTION_MESSAGE.format(user=member.mention))

                    message_sent = True
                except Exception:
                    log.exception(f"Unable to send rejection message to user: {member}")

                await member.kick(reason="DEFCON active, user is too new")

                message = (
                    f"{member.name}#{member.discriminator} (`{member.id}`) "
                    f"was denied entry because their account is too new."
                )

                if not message_sent:
                    message = f"{message}\n\nUnable to send rejection message via DM; they probably have DMs disabled."

                await self.modlog.send_log_message(
                    Icons.defcon_denied, COLOUR_RED, "Entry denied",
                    message, member.avatar_url_as(static_format="png")
                )

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
        except Exception as e:
            log.exception("Unable to update DEFCON settings.")
            await ctx.send(
                f"{Emojis.defcon_enabled} DEFCON enabled.\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )

            await self.modlog.send_log_message(
                Icons.defcon_enabled, COLOUR_GREEN, "DEFCON enabled",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                f"**Days:** {self.days.days}\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )
        else:
            await ctx.send(f"{Emojis.defcon_enabled} DEFCON enabled.")

            await self.modlog.send_log_message(
                Icons.defcon_enabled, COLOUR_GREEN, "DEFCON enabled",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                f"**Days:** {self.days.days}\n\n"
            )

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
        except Exception as e:
            log.exception("Unable to update DEFCON settings.")
            await ctx.send(
                f"{Emojis.defcon_disabled} DEFCON disabled.\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )

            await self.modlog.send_log_message(
                Icons.defcon_disabled, COLOUR_RED, "DEFCON disabled",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )
        else:
            await ctx.send(f"{Emojis.defcon_disabled} DEFCON disabled.")

            await self.modlog.send_log_message(
                Icons.defcon_disabled, COLOUR_RED, "DEFCON disabled",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)"
            )

    @with_role(Roles.admin, Roles.owner)
    @command(name="defcon", aliases=["defcon()", "defcon.status", "defcon.status()"])
    async def defcon(self, ctx: Context):
        """
        Check the current status of DEFCON mode.
        """

        embed = Embed(
            colour=Colour.blurple(), title="DEFCON Status",
            description=f"**Enabled:** {self.enabled}\n"
                        f"**Days:** {self.days.days}"
        )

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
        except Exception as e:
            log.exception("Unable to update DEFCON settings.")
            await ctx.send(
                f"{Emojis.defcon_updated} DEFCON days updated; accounts must be {days} "
                f"days old to join to the server.\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )

            await self.modlog.send_log_message(
                Icons.defcon_updated, Colour.blurple(), "DEFCON updated",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                f"**Days:** {self.days.days}\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )
        else:
            await ctx.send(
                f"{Emojis.defcon_updated} DEFCON days updated; accounts must be {days} days old to join to the server"
            )

            await self.modlog.send_log_message(
                Icons.defcon_updated, Colour.blurple(), "DEFCON updated",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                f"**Days:** {self.days.days}"
            )


def setup(bot: Bot):
    bot.add_cog(Defcon(bot))
    log.info("Cog loaded: Defcon")
