import discord
from discord.ext.commands import Cog
from discord.ext.commands import Context

from detect import send_dm

from bot.bot import Bot
from bot.log import get_logger

import json
from pathlib import Path


log = get_logger(__name__)


# Assumes a `channel_word_trackers` dictionary is defined elsewhere. This list is for testing purposes.
"""channel_word_trackers = {
    1341835774915514386: {
    "wow": {
        166578600798060544}}}"""
class Detect(Cog):
    """Detects listed words in listed channels and notifies listed users by DMing them"""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.json_path =Path("/tmp/word_trackers.json")
        self.channel_word_trackers = {}

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listens for a message and checks its relevant"""

        # Ignore bot messages
        if message.author.bot:
            return


        if not self.json_path.exists():
            self.channel_word_trackers = {}
        try:
            self.channel_word_trackers = json.loads(self.json_path.read_text())
        except Exception as e:
            log.error(f"Failed to read JSON: {e}")
            self.channel_word_trackers = {}

        # Check if this channel has any tracked words
        channel_id = message.channel.id
        if channel_id not in self.channel_word_trackers:
            return

        # Get the words tracked for this channel
        tracked_words_for_channel = self.channel_word_trackers[channel_id]
        content_lower = message.content.lower()

        # Check each tracked word in this channel
        for word, user_ids in tracked_words_for_channel.items():
            if word in content_lower:
                if is_malicious(message):
                    continue
                else:
                    # If not spam, DM all users who track this word in this channel
                    for user_id in user_ids:
                        user = self.bot.get_user(user_id)
                        if user is None:
                            try:
                                user = await self.bot.fetch_user(user_id)
                            except discord.HTTPException as exc:
                                log.exception(f"Failed to fetch user {user_id}: {exc}")
                                return
                        await send_dm(
                                user,
                                f"A tracked word ('{word}') was mentioned by {message.author.mention} in {message.channel.mention}."
                            )





async def setup(bot: Bot) -> None:
    """Load the Detect cog."""
    await bot.add_cog(Detect(bot))
