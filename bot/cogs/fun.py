import logging
from textwrap import dedent

from discord import Colour, Embed, Message, RawReactionActionEvent
from discord.ext.commands import Bot

from bot.constants import Channels, Guild, Roles

RESPONSES = {
    "_pokes {us}_": "_Pokes {them}_",
    "_eats {us}_": "_Tastes slimy and snake-like_",
    "_pets {us}_": "_Purrs_"
}

STAR_EMOJI = "\u2b50"
# TODO: Remove test role id 231157479273267201
ALLOWED_TO_STAR = (Roles.admin, Roles.moderator, Roles.owner, Roles.helpers, 231157479273267201)

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

    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        starboard = self.bot.get_channel(Channels.starboard)
        if not starboard:
            return log.warning("Starboard TextChannel was not found.")

        emoji = payload.emoji

        if emoji.is_custom_emoji():
            # This might be redundant given the check below.
            return

        if emoji.name != STAR_EMOJI:
            log.debug(f"{emoji.name} was reacted")
            return

        if payload.guild_id != Guild.id:
            # We only do the starboard in the guild
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)

        if not member or not any(role == member.top_role.id for role in ALLOWED_TO_STAR):
            return log.debug(
                f"Star reaction was added by {str(member)} "
                "but they lack the permissions to post on starboard. "
            )

        # TODO: Check if message was stared already.

        channel = guild.get_channel(payload.channel_id)
        message = await channel.get_message(payload.message_id)

        embed = Embed()
        embed.description = dedent(
            f"""
            {message.content}

            [Jump to message]({message.jump_url})
            """
        )
        author = message.author
        embed.timestamp = message.created_at
        embed.set_author(name=author.display_name, icon_url=author.avatar_url)
        embed.colour = Colour.gold()

        await starboard.send(
            f"{STAR_EMOJI} {channel.mention}",
            embed=embed
        )


def setup(bot):
    bot.add_cog(Fun(bot))
    log.info("Cog loaded: Fun")
