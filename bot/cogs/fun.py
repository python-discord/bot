import logging
from textwrap import dedent

from discord import Colour, Embed, Message, RawReactionActionEvent
from discord.utils import get
from discord.ext.commands import Bot

from bot.constants import Channels, Guild, Keys, Roles, URLs

RESPONSES = {
    "_pokes {us}_": "_Pokes {them}_",
    "_eats {us}_": "_Tastes slimy and snake-like_",
    "_pets {us}_": "_Purrs_"
}

STAR_EMOJI = "\u2b50"
LVL2_STAR = "\U0001f31f"
LVL3_STAR = "\U0001f4ab"
LVL4_STAR = "\u2728"

# TODO: Remove test role id 231157479273267201
ALLOWED_TO_STAR = (Roles.admin, Roles.moderator, Roles.owner, Roles.helpers, 231157479273267201)

log = logging.getLogger(__name__)


class Fun:
    """
    Fun, entirely useless stuff
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-Key": Keys.site_api}
        self.star_msg_map = {}

    async def on_ready(self):
        keys = list(RESPONSES.keys())

        for key in keys:
            changed_key = key.replace("{us}", self.bot.user.mention)

            if key != changed_key:
                RESPONSES[changed_key] = RESPONSES[key]
                del RESPONSES[key]

        # Get all starred messages to populate star to msg map
        response = await self.bot.http_session.get(
            url=URLs.site_starboard_api,
            headers=self.headers
        )

        messages = response["messages"]
        for message in messages:
            key = message["bot_message_id"]
            value = message["jump_to_url"]
            self.star_msg_map[key] = value

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

        for starboard_msg_id, url in self.star_msg_map.items():
            # Message is already on the starboard
            # Checks if the id is in the jump to url
            if str(payload.message_id) in url:
                starboard_msg = await starboard.get_message(starboard_msg_id)
                count = self.increment_starcount(starboard_msg, message)
                return log.debug(f"Incremented starboard star count for `{message.id}` to {count}")

        # Message was not starred before, let's add it to the board!
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

        msg = await starboard.send(
            f"1 {STAR_EMOJI} {channel.mention}",
            embed=embed
        )

        response = await self.bot.http_session.post(
            url=URLs.site_starboard_api,
            headers=self.headers,
            json={
                "message_id": message.id,
                "bot_message_id": msg.id,
                "guild_id": Guild.id,
                "channel_id": message.channel.id,
                "author_id": author.id,
                "jump_to_url": message.jump_url
            }
        )

        if response["message"] != "ok":
            # Delete it from the starboard before anyone notices our flaws in life.
            await msg.delete()
            return log.warning(
                "Failed to post starred message "
                f"{response['message']}"
            )

        self.star_msg_map[msg.id] = message.jump_url

    async def increment_starcount(self, star: Message, msg: Message):
        reaction = get(msg.reactions, name=STAR_EMOJI)

        if not reaction:
            log.warning(
                "increment_starcount was called, but could not find a star reaction"
                " on the original message"
            )
            return

        count = reaction.count
        if count < 5:
            star = STAR_EMOJI
        elif 5 >= count < 10:
            star = LVL2_STAR
        elif 10 >= count < 15:
            star = LVL3_STAR
        elif count >= 15:
            star = LVL4_STAR

        embed = star.embeds[0]
        await msg.edit(
            content=f"{reaction.count} {star} {msg.channel.mention}",
            embed=embed
        )


def setup(bot):
    bot.add_cog(Fun(bot))
    log.info("Cog loaded: Fun")
