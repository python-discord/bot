import logging
import random

from discord import Colour, Embed, Member
from discord.errors import Forbidden
from discord.ext.commands import Bot, Context, command

from bot.constants import (
    Channels, Keys,
    NEGATIVE_REPLIES, POSITIVE_REPLIES,
    Roles, URLs
)
from bot.decorators import with_role


log = logging.getLogger(__name__)


class Superstarify:
    """
    A set of commands to moderate terrible nicknames.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}

    async def on_member_update(self, before, after):
        """
        This event will trigger when someone changes their name.
        At this point we will look up the user in our database and check
        whether they are allowed to change their names, or if they are in
        superstar-prison. If they are not allowed, we will change it back.
        :return:
        """

        if before.display_name == after.display_name:
            return  # User didn't change their nickname. Abort!

        log.debug(
            f"{before.display_name} is trying to change their nickname to {after.display_name}. "
            "Checking if the user is in superstar-prison..."
        )

        response = await self.bot.http_session.get(
            URLs.site_superstarify_api,
            headers=self.headers,
            params={"user_id": str(before.id)}
        )

        response = await response.json()

        if response and response.get("end_timestamp") and not response.get("error_code"):
            if after.display_name == response.get("forced_nick"):
                return  # Nick change was triggered by this event. Ignore.

            log.debug(
                f"{after.display_name} is currently in superstar-prison. "
                f"Changing the nick back to {before.display_name}."
            )
            await after.edit(nick=response.get("forced_nick"))
            try:
                await after.send(
                    "You have tried to change your nickname on the **Python Discord** server "
                    f"from **{before.display_name}** to **{after.display_name}**, but as you "
                    "are currently in superstar-prison, you do not have permission to do so. "
                    "You will be allowed to change your nickname again at the following time:\n\n"
                    f"**{response.get('end_timestamp')}**."
                )
            except Forbidden:
                log.warning(
                    "The user tried to change their nickname while in superstar-prison. "
                    "This led to the bot trying to DM the user to let them know they cannot do that, "
                    "but the user had either blocked the bot or disabled DMs, so it was not possible "
                    "to DM them, and a discord.errors.Forbidden error was incurred."
                )

    @command(name='superstarify', aliases=('force_nick', 'ss'))
    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    async def superstarify(self, ctx: Context, member: Member, duration: str, *, forced_nick: str = None):
        """
        This command will force a random superstar name (like Taylor Swift) to be the user's
        nickname for a specified duration. If a forced_nick is provided, it will use that instead.

        :param ctx: Discord message context
        :param ta:
        If provided, this function shows data for that specific tag.
        If not provided, this function shows the caller a list of all tags.
        """

        log.debug(
            f"Attempting to superstarify {member.display_name} for {duration}. "
            f"forced_nick is set to {forced_nick}."
        )

        embed = Embed()
        embed.colour = Colour.blurple()

        params = {
            "user_id": str(member.id),
            "duration": duration
        }

        if forced_nick:
            params["forced_nick"] = forced_nick

        response = await self.bot.http_session.post(
            URLs.site_superstarify_api,
            headers=self.headers,
            json=params
        )

        response = await response.json()

        if "error_message" in response:
            log.warning(
                "Encountered the following error when trying to superstarify the user:\n"
                f"{response.get('error_message')}"
            )
            embed.colour = Colour.red()
            embed.title = random.choice(NEGATIVE_REPLIES)
            embed.description = response.get("error_message")
            return await ctx.send(embed=embed)

        else:
            forced_nick = response.get('forced_nick')
            end_time = response.get("end_timestamp")
            image_url = response.get("image_url")

            embed.title = "Congratulations!"
            embed.description = (
                f"Your previous nickname, **{member.display_name}**, was so bad that we have decided to change it. "
                f"Your new nickname will be **{forced_nick}**.\n\n"
                f"You will be unable to change your nickname until \n**{end_time}**.\n\n"
                "If you're confused by this, please read our "
                "[official nickname policy](https://pythondiscord.com/about/rules#nickname-policy)."
            )
            embed.set_image(url=image_url)

            # Log to the mod_log channel
            log.trace("Logging to the #mod-log channel. This could fail because of channel permissions.")
            mod_log = self.bot.get_channel(Channels.modlog)
            await mod_log.send(
                f":middle_finger: {member.name}#{member.discriminator} (`{member.id}`) "
                f"has been superstarified by **{ctx.author.name}**. Their new nickname is `{forced_nick}`. "
                f"They will not be able to change their nickname again until **{end_time}**"
            )

            # Change the nick and return the embed
            log.debug("Changing the users nickname and sending the embed.")
            await member.edit(nick=forced_nick)
            await ctx.send(embed=embed)

    @command(name='unsuperstarify', aliases=('release_nick', 'uss'))
    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    async def unsuperstarify(self, ctx: Context, member: Member):
        """
        This command will remove the entry from our database, allowing the user
        to once again change their nickname.

        :param ctx: Discord message context
        :param member: The member to unsuperstarify
        """

        log.debug(f"Attempting to unsuperstarify the following user: {member.display_name}")

        embed = Embed()
        embed.colour = Colour.blurple()

        response = await self.bot.http_session.delete(
            URLs.site_superstarify_api,
            headers=self.headers,
            json={"user_id": str(member.id)}
        )

        response = await response.json()
        embed.description = "User has been released from superstar-prison."
        embed.title = random.choice(POSITIVE_REPLIES)

        if "error_message" in response:
            embed.colour = Colour.red()
            embed.title = random.choice(NEGATIVE_REPLIES)
            embed.description = response.get("error_message")
            log.warning(
                f"Error encountered when trying to unsuperstarify {member.display_name}:\n"
                f"{response}"
            )

        log.debug(f"{member.display_name} was successfully released from superstar-prison.")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Superstarify(bot))
    log.info("Cog loaded: Superstarify")
