import asyncio
import logging
from textwrap import dedent
from typing import Tuple, Optional

from discord import (
    Colour, Embed, Forbidden, HTTPException,
    Message, PartialEmoji, RawReactionActionEvent,
    Reaction, TextChannel
)
from discord.ext.commands import Bot, command, CommandError, has_role
from discord.utils import get

from bot.constants import Channels, Guild, Keys, Roles, URLs
from bot.decorators import with_role

RESPONSES = {
    "_pokes {us}_": "_Pokes {them}_",
    "_eats {us}_": "_Tastes slimy and snake-like_",
    "_pets {us}_": "_Purrs_"
}

LVL1_STAR = "\u2b50"
LVL2_STAR = "\U0001f31f"
LVL3_STAR = "\U0001f4ab"
LVL4_STAR = "\u2728"

YES_EMOJI = "\u2705"
NO_EMOJI = "\u274e"

THRESHOLDS = {
    LVL1_STAR: 1,
    LVL2_STAR: 5,
    LVL3_STAR: 10,
    LVL4_STAR: 20
}

ALLOWED_TO_STAR = (Roles.admin, Roles.moderator, Roles.owner, Roles.helpers)

log = logging.getLogger(__name__)


class NoStarboardException(CommandError):
    pass


class Fun:
    """
    Fun, entirely useless stuff
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-Key": Keys.site_api}
        self.star_msg_map = {}

        keys = list(RESPONSES.keys())

        for key in keys:
            changed_key = key.replace("{us}", self.bot.user.mention)

            if key != changed_key:
                RESPONSES[changed_key] = RESPONSES[key]
                del RESPONSES[key]

        self.bot.loop.create_task(self.async_init())

    async def async_init(self):
        # Get all starred messages to populate star to msg map
        response = await self.bot.http_session.get(
            url=URLs.site_starboard_api,
            headers=self.headers
        )
        json = await response.json()
        messages = json["messages"]

        for message in messages:
            key = message["message_id"]
            value = message["bot_message_id"]
            self.star_msg_map[key] = value

        log.debug(f"Populated star_msg_map: {self.star_msg_map}")

    async def on_message(self, message: Message):
        if message.channel.id != Channels.bot:
            return

        content = message.content

        if content and content[0] == "*" and content[-1] == "*":
            content = f"_{content[1:-1]}_"

        response = RESPONSES.get(content)

        if response:
            log.debug(
                f"{message.author} said '{message.clean_content}'. Responding with '{response}'.")
            await message.channel.send(response.format(them=message.author.mention))

    @command(name="deletestarboard")
    @with_role(Roles.owner)
    async def delete_all_star_entries(self, ctx):
        msg = await ctx.send("This will delete all entries from the starboard, are you sure?")
        await msg.add_reaction(YES_EMOJI)
        await msg.add_reaction(NO_EMOJI)

        def check(r, u):
            if r.emoji != YES_EMOJI and r.emoji != NO_EMOJI:
                return False

            if not get(u.roles, id=Roles.owner):
                return False

            if u.id != ctx.author.id:
                return False
            return True

        try:
            reaction, _ = await self.bot.wait_for(
                "reaction_add",
                check=check,
                timeout=60
            )
        except asyncio.TimeoutError:
            log.debug("No reaction to delete all starboard entries were given.")
            return

        if reaction.emoji == NO_EMOJI:
            log.info("No was selected to deleting all entries from starboard")
            return

        if reaction.emoji == YES_EMOJI:
            # Can never be too sure here.
            response = await self.bot.http_session.delete(
                url=f"{URLs.site_starboard_api}/delete",
                headers=self.headers,
            )
            if response.status != 200:
                log.warning("Deleting all starboard entries failed")
                text_resp = await response.text()
                log.warning(text_resp)
            else:
                log.info("All entries from starboard was deleted from site db.")

    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        if payload.guild_id != Guild.id:
            return log.debug("Reaction was not added in the correct guild.")

        starboard = self.bot.get_channel(Channels.starboard)
        try:
            original, star_msg = await self.get_messages(payload, starboard)
        except (KeyError, NoStarboardException) as e:
            return log.exception(e)

    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.guild_id != Guild.id:
            return log.debug("Reaction was not added in the correct guild.")

        if payload.emoji.name != LVL1_STAR:
            return log.debug("Invalid emoji was reacted")

        starboard = self.bot.get_channel(Channels.starboard)

        try:
            original, star_msg = await self.get_messages(payload, starboard)
        except (KeyError, NoStarboardException) as e:
            return log.exception(e)

        reaction = get(original.reactions, emoji=LVL1_STAR)
        count = reaction.count

        if reaction is None:
            await self.delete_star(original, star_msg)
            return log.debug("There was not any reacted stars on the original message.")

        if count < THRESHOLDS[LVL1_STAR]:
            return log.debug("Reaction count did not meet threshold.")

        if star_msg is None:
            await self.post_new_entry(original, starboard)
            log.debug("star_msg was None, creating the starboard entry.")
        else:
            await self.change_starcount(original, star_msg)
            log.debug("star_msg was given, updating existing starboard entry")

    async def get_messages(
        self,
        payload: RawReactionActionEvent,
        starboard: TextChannel
    ) -> Tuple[Message, Optional[Message]]:
        """
        Method to fetch the message instance the payload represents,
        secondly checks the cache and API for an associated starboard entry

        There may not be a starboard entry, index 1 of tuple may be None.
        :param payload: The payload provided by on_raw_reaction_x
        :param starboard: A Discord.TextChannel where starboard entries are posted
        :return: Tuple[discord.Message, Optional[discord.Message]]
                 Returns the message instance that was starred and the associated
                 starboard message instance, if there is one else None.
        """

        if starboard is None:
            log.warning("Starboard TextChannel was not found!")
            raise NoStarboardException()

        # Better safe than sorry.
        try:
            original_channel = self.bot.get_channel(payload.channel_id)
        except KeyError as e:
            log.warning("Payload did not have a channel_id key")
            raise e

        try:
            original = await original_channel.get_message(payload.message_id)
        except KeyError as e:
            log.warning("Payload did not have a message_id key")
            raise e

        try:
            # See if it's stored in cache
            star_msg_id = self.star_msg_map[payload.message_id]
            star_msg = await starboard.get_message(star_msg_id)
            return original, star_msg
        except KeyError as e:
            log.debug(
                "star_msg_map did not have a starred message, checking API...")

        # Message was not in cache, but could be stored online
        url = f"{URLs.site_starboard_api}?message_id={payload.message_id}"
        response = await self.bot.http_session.get(
            url=url,
            headers=self.headers
        )
        json_data = await response.json()

        try:
            entry = json_data["message"]
        except KeyError as e:
            log.debug(
                "Response json from message_id endpoint didn't return a message key.")
            return original, None

        star_msg = None

        if entry is not None:
            star_msg = await starboard.get_message(entry.get("bot_message_id"))

        if star_msg is None:
            log.debug("No starboard message was found from cache or API")

        # If starboard message is not found star_msg is returned as None, and handled higher up.
        return original, star_msg

    async def post_new_entry(self, original: Message, starboard: TextChannel) -> None:
        """
        Posts a new entry to the starboard channel, constructs an embed with
        the channel, star count, message, author, avatar, and a jump to url.

        Posts the starboard entry to the starboard endpoint for storage.
        :param original: The original message that was starred
        :param starboard: The TextChannel the entry is posted to
        :return: None
        """

        embed = Embed()
        embed.description = dedent(
            f"""
            {original.content}

            [Jump to message]({original.jump_url})
            """
        )

        author = original.author
        embed.timestamp = original.created_at
        embed.set_author(name=author.display_name, icon_url=author.avatar_url)
        embed.colour = Colour.gold()

        try:
            star_msg = await starboard.send(
                f"1 {LVL1_STAR} {original.channel.mention}",
                embed=embed
            )
            log.debug(
                "Posted starboard entry embed to the starboard successfully.")
        except Forbidden as e:
            log.warning(
                f"Bot does not have permission to post in starboard channel ({starboard.id})")
            log.exception(e)
            return
        except HTTPException as e:
            log.warning("Something went wrong posting message to starboard")
            log.exception(e)
            return

        response = await self.bot.http_session.post(
            url=URLs.site_starboard_api,
            headers=self.headers,
            json={
                "message_id": original.id,
                "bot_message_id": star_msg.id,
                "guild_id": Guild.id,
                "channel_id": original.channel.id,
                "author_id": author.id,
                "jump_to_url": original.jump_url
            }
        )

        if response.status != 200:
            # Delete it from the starboard before anyone notices our flaws in life.
            json_resp = await response.json()
            await star_msg.delete()
            return log.warning(
                "Failed to post starred message with "
                f"status code {response.status} "
                f"response: {json_resp.get('response')}"
            )

        log.debug("Successfully posted json to endpoint, storing in cache...")
        self.star_msg_map[original.id] = star_msg.id

    async def change_starcount(self, original: Message, star_msg: Message):
        pass

    async def delete_star(self, original: Message, star: Message):
        """
        Delete an entry on the starboard

        :param original: Message the starboard references
        :param star: Starboard message
        """

        deleting_failed = False

        try:
            await star.delete()
        except Forbidden:
            log.warning(
                "Failed to delete starboard entry, missing permissions!")
            deleting_failed = True
        except HTTPException:
            log.warning("Failed to delete starboard entry, HTTPexception.")
            deleting_failed = True

        url = f"{URLs.site_starboard_api}?message_id={original.id}"
        resp = await self.bot.http_session.delete(
            url=url,
            header=self.headers
        )

        if resp.status != 200:
            log.warning(
                f"Failed to delete {original.id} from starboard db, status {resp.status}")
            if deleting_failed:
                log.warning("Failed to delete the starboard message, see previous warnings. "
                            "but database entry was not deleted.")
        else:
            log.info("Successfully deleted starboard entry from db")
            log.debug("Deleting entry from cache")
            try:
                del self.star_msg_map[original.id]
            except KeyError:
                log.debug(
                    f"Failed to delete from cache, KeyError - id: {original.id}")


def setup(bot):
    bot.add_cog(Fun(bot))
    log.info("Cog loaded: Fun")
