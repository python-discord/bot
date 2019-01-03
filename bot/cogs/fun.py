import logging
from textwrap import dedent

from discord import Colour, Embed, Message, RawReactionActionEvent
from discord.ext.commands import Bot
from discord.utils import get

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

ALLOWED_TO_STAR = (Roles.admin, Roles.moderator, Roles.owner, Roles.helpers)

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
        json = await response.json()
        messages = json["messages"]

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

    async def star_reaction_checks(self, payload: RawReactionActionEvent):
        starboard = self.bot.get_channel(Channels.starboard)

        if not starboard:
            log.warning("Starboard TextChannel was not found.")
            return False, None

        emoji = payload.emoji

        if emoji.name != STAR_EMOJI or payload.guild_id != Guild.id:
            return False, None

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)

        if not member or not any(role == member.top_role.id for role in ALLOWED_TO_STAR):
            log.debug(
                f"Star reaction was added by {str(member)} "
                "but they lack the permissions to post on starboard. "
            )
            return False, None

        channel = guild.get_channel(payload.channel_id)
        message = await channel.get_message(payload.message_id)

        for starboard_msg_id, url in self.star_msg_map.items():
            # Checks if the id is in the jump to url
            if str(payload.message_id) in url:
                starboard_msg = await starboard.get_message(starboard_msg_id)
                await self.change_starcount(starboard_msg, message)
                break
        else:
            # Check the api just in case
            url = f"{URLs.site_starboard_api}?message_id={message.id}"
            response = await self.bot.http_session.get(
                url=url,
                headers=self.headers
            )
            json_data = await response.json()
            entry = json_data.get("message")

            if entry is None:
                return False, None

            self.star_msg_map[entry["message_id"]] = entry["jump_to_url"]

        return True, message

    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        await self.star_reaction_checks(payload)

    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        result, message = await self.star_reaction_checks(payload)
        if not result:
            return

        starboard = self.bot.get_channel(Channels.starboard)

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
            f"1 {STAR_EMOJI} {message.channel.mention}",
            embed=embed
        )

        response = await self.bot.http_session.post(
            url=URLs.site_starboard_api,
            headers=self.headers,
            json={
                "message_id": str(message.id),
                "bot_message_id": str(msg.id),
                "guild_id": str(Guild.id),
                "channel_id": str(message.channel.id),
                "author_id": str(author.id),
                "jump_to_url": message.jump_url
            }
        )
        json = await response.json()

        if json.get("message") != "ok":
            # Delete it from the starboard before anyone notices our flaws in life.
            await msg.delete()
            return log.warning(
                "Failed to post starred message "
                f"{json.get('error_message')}"
            )

        self.star_msg_map[msg.id] = message.jump_url

    async def change_starcount(self, star: Message, msg: Message):
        """
        Edits the starboard message to show the current amount
        of stars on the starred message.

        :param star: Starboard message
        :param msg: Message starboard references
        """

        reaction = get(msg.reactions, emoji=STAR_EMOJI)

        if not reaction:
            log.warning(
                "increment_starcount was called, but could not find a star reaction "
                "on the original message"
            )
            return await self.delete_star(star, msg)

        count = reaction.count

        if count < 5:
            star_emoji = STAR_EMOJI
        elif 5 >= count < 10:
            star_emoji = LVL2_STAR
        elif 10 >= count < 15:
            star_emoji = LVL3_STAR
        else:
            star_emoji = LVL4_STAR

        embed = star.embeds[0]

        if count > 0:
            await star.edit(
                content=f"{reaction.count} {star_emoji} {msg.channel.mention}",
                embed=embed
            )
            log.debug(f"Changed starboard star count for `{msg.id}` to {count}")

        else:
            # The star count went down to 0, remove it from the board
            await self.delete_star(star, msg)

    async def delete_star(self, star: Message, msg: Message):
        """
        Delete an entry to the starboard

        :param star: Starboard message
        :param msg: Message the starboard references
        """

        try:
            await star.delete()
        except Exception as e:
            log.info(e)

        url = f"{URLs.site_starboard_api}?message_id={msg.id}"
        resp = await self.bot.http_session.delete(
            url=url,
            headers=self.headers,
        )
        resp_data = await resp.json()

        if not resp_data.get("success"):
            log.warning(f"Failed to delete {msg.id} from starboard db")
        else:
            log.info("Successfully deleted starboard entry")
            try:
                del self.star_msg_map[msg.id]
            except KeyError:
                pass


def setup(bot):
    bot.add_cog(Fun(bot))
    log.info("Cog loaded: Fun")
