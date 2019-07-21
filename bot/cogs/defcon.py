import logging
from datetime import datetime, timedelta

from discord import Colour, Embed, Member
from discord.ext.commands import Bot, Context, group

from bot.cogs.modlog import ModLog
from bot.constants import Channels, Colours, Emojis, Event, Icons, Keys, Roles
from bot.decorators import with_role

log = logging.getLogger(__name__)

REJECTION_MESSAGE = """
Hi, {user} - Thanks for your interest in our server!

Due to a current (or detected) cyberattack on our community, we've limited access to the server for new accounts. Since
your account is relatively new, we're unable to provide access to the server at this time.

Even so, thanks for joining! We're very excited at the possibility of having you here, and we hope that this situation
will be resolved soon. In the meantime, please feel free to peruse the resources on our site at
<https://pythondiscord.com/>, and have a nice day!
"""

BASE_CHANNEL_TOPIC = "Python Discord Defense Mechanism"


class Defcon:
    """Time-sensitive server defense mechanisms"""
    days = None  # type: timedelta
    enabled = False  # type: bool

    def __init__(self, bot: Bot):
        self.bot = bot
        self.days = timedelta(days=0)
        self.headers = {"X-API-KEY": Keys.site_api}

    @property
    def mod_log(self) -> ModLog:
        return self.bot.get_cog("ModLog")

    async def on_ready(self):
        try:
            response = await self.bot.api_client.get('bot/bot-settings/defcon')
            data = response['data']

        except Exception:  # Yikes!
            log.exception("Unable to get DEFCON settings!")
            await self.bot.get_channel(Channels.devlog).send(
                f"<@&{Roles.admin}> **WARNING**: Unable to get DEFCON settings!"
            )

        else:
            if data["enabled"]:
                self.enabled = True
                self.days = timedelta(days=data["days"])
                log.warning(f"DEFCON enabled: {self.days.days} days")

            else:
                self.enabled = False
                self.days = timedelta(days=0)
                log.warning(f"DEFCON disabled")

            await self.update_channel_topic()

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

                await self.mod_log.send_log_message(
                    Icons.defcon_denied, Colours.soft_red, "Entry denied",
                    message, member.avatar_url_as(static_format="png")
                )

    @group(name='defcon', aliases=('dc',), invoke_without_command=True)
    @with_role(Roles.admin, Roles.owner)
    async def defcon_group(self, ctx: Context):
        """Check the DEFCON status or run a subcommand."""

        await ctx.invoke(self.bot.get_command("help"), "defcon")

    @defcon_group.command(name='enable', aliases=('on', 'e'))
    @with_role(Roles.admin, Roles.owner)
    async def enable_command(self, ctx: Context):
        """
        Enable DEFCON mode. Useful in a pinch, but be sure you know what you're doing!

        Currently, this just adds an account age requirement. Use !defcon days <int> to set how old an account must
        be, in days.
        """

        self.enabled = True

        try:
            await self.bot.api_client.put(
                'bot/bot-settings/defcon',
                json={
                    'name': 'defcon',
                    'data': {
                        'enabled': True,
                        # TODO: retrieve old days count
                        'days': 0
                    }
                }
            )

        except Exception as e:
            log.exception("Unable to update DEFCON settings.")
            await ctx.send(
                f"{Emojis.defcon_enabled} DEFCON enabled.\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )

            await self.mod_log.send_log_message(
                Icons.defcon_enabled, Colours.soft_green, "DEFCON enabled",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                f"**Days:** {self.days.days}\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )

        else:
            await ctx.send(f"{Emojis.defcon_enabled} DEFCON enabled.")

            await self.mod_log.send_log_message(
                Icons.defcon_enabled, Colours.soft_green, "DEFCON enabled",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                f"**Days:** {self.days.days}\n\n"
            )

        await self.update_channel_topic()

    @defcon_group.command(name='disable', aliases=('off', 'd'))
    @with_role(Roles.admin, Roles.owner)
    async def disable_command(self, ctx: Context):
        """
        Disable DEFCON mode. Useful in a pinch, but be sure you know what you're doing!
        """

        self.enabled = False

        try:
            await self.bot.api_client.put(
                'bot/bot-settings/defcon',
                json={
                    'data': {
                        'days': 0,
                        'enabled': False
                    },
                    'name': 'defcon'
                }
            )
        except Exception as e:
            log.exception("Unable to update DEFCON settings.")
            await ctx.send(
                f"{Emojis.defcon_disabled} DEFCON disabled.\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )

            await self.mod_log.send_log_message(
                Icons.defcon_disabled, Colours.soft_red, "DEFCON disabled",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )
        else:
            await ctx.send(f"{Emojis.defcon_disabled} DEFCON disabled.")

            await self.mod_log.send_log_message(
                Icons.defcon_disabled, Colours.soft_red, "DEFCON disabled",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)"
            )

        await self.update_channel_topic()

    @defcon_group.command(name='status', aliases=('s',))
    @with_role(Roles.admin, Roles.owner)
    async def status_command(self, ctx: Context):
        """
        Check the current status of DEFCON mode.
        """

        embed = Embed(
            colour=Colour.blurple(), title="DEFCON Status",
            description=f"**Enabled:** {self.enabled}\n"
                        f"**Days:** {self.days.days}"
        )

        await ctx.send(embed=embed)

    @defcon_group.command(name='days')
    @with_role(Roles.admin, Roles.owner)
    async def days_command(self, ctx: Context, days: int):
        """
        Set how old an account must be to join the server, in days, with DEFCON mode enabled.
        """

        self.days = timedelta(days=days)

        try:
            await self.bot.api_client.put(
                'bot/bot-settings/defcon',
                json={
                    'data': {
                        'days': days,
                        'enabled': True
                    },
                    'name': 'defcon'
                }
            )
        except Exception as e:
            log.exception("Unable to update DEFCON settings.")
            await ctx.send(
                f"{Emojis.defcon_updated} DEFCON days updated; accounts must be {days} "
                f"days old to join to the server.\n\n"
                "**There was a problem updating the site** - This setting may be reverted when the bot is "
                "restarted.\n\n"
                f"```py\n{e}\n```"
            )

            await self.mod_log.send_log_message(
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

            await self.mod_log.send_log_message(
                Icons.defcon_updated, Colour.blurple(), "DEFCON updated",
                f"**Staffer:** {ctx.author.name}#{ctx.author.discriminator} (`{ctx.author.id}`)\n"
                f"**Days:** {self.days.days}"
            )

        await self.update_channel_topic()

    async def update_channel_topic(self):
        """
        Update the #defcon channel topic with the current DEFCON status
        """

        if self.enabled:
            day_str = "days" if self.days.days > 1 else "day"
            new_topic = f"{BASE_CHANNEL_TOPIC}\n(Status: Enabled, Threshold: {self.days.days} {day_str})"
        else:
            new_topic = f"{BASE_CHANNEL_TOPIC}\n(Status: Disabled)"

        self.mod_log.ignore(Event.guild_channel_update, Channels.defcon)
        defcon_channel = self.bot.guilds[0].get_channel(Channels.defcon)
        await defcon_channel.edit(topic=new_topic)


def setup(bot: Bot):
    bot.add_cog(Defcon(bot))
    log.info("Cog loaded: Defcon")
