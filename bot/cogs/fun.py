import logging
from textwrap import dedent

from discord import Colour, Embed, Message, User
from discord.ext.commands import Bot

from bot.constants import Channels, Roles

RESPONSES = {
    "_pokes {us}_": "_Pokes {them}_",
    "_eats {us}_": "_Tastes slimy and snake-like_",
    "_pets {us}_": "_Purrs_"
}

STAR_EMOJI = "\u2b50"
ALLOWED_TO_STAR = (Roles.admin, Roles.moderator, Roles.owner, Roles.helpers)

log = logging.getLogger(__name__)


class Fun:
    """
    Fun, entirely useless stuff
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    async def on_ready(self):
        keys = list(RESPONSES.keys())

        for key in keys:
            changed_key = key.replace("{us}", self.bot.user.mention)

            if key != changed_key:
                RESPONSES[changed_key] = RESPONSES[key]
                del RESPONSES[key]

    async def on_message(self, message: Message):
        if message.channel.id != Channels.bot:
            return

        content = message.content

        if content and content[0] == "*" and content[-1] == "*":
            content = f"_{content[1:-1]}_"

        response = RESPONSES.get(content)

        if response:
            log.debug(f"{message.author} said '{message.clean_content}'. Responding with '{response}'.")
            await message.channel.send(response.format(them=message.author.mention))

    async def on_reaction_add(self, reaction, user):
        starboard = self.bot.get_channel(Channels.starboard)
        if not starboard:
            return log.warning("Starboard TextChannel was not found.")

        if reaction.emoji != STAR_EMOJI:
            return

        if isinstance(user, User):
            return  # We only do the starboard in the guild, so this would be a member

        if not any(role == user.top_role.id for role in ALLOWED_TO_STAR):
            return log.debug(
                f"Star reaction was added by {str(user)} "
                "but they lack the permissions to post on starboard"
            )

        # TODO: Check if message was stared already

        message = reaction.message
        content = message.content
        author = message.author
        channel = message.channel
        msg_jump = message.jump_url
        created_at = message.created_at

        embed = Embed()
        embed.description = dedent(
            f"""
            {content}
            
            [Jump to message]({msg_jump})
            """
        )
        embed.timestamp = created_at
        embed.set_author(name=author.display_name, icon_url=author.avatar_url)
        embed.colour = Colour.gold()

        await starboard.send(
            f"{STAR_EMOJI} {channel.mention}",
            embed=embed
        )


def setup(bot):
    bot.add_cog(Fun(bot))
    log.info("Cog loaded: Fun")
