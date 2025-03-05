import discord
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.log import get_logger

log = get_logger(__name__)


# Assumes a `channel_word_trackers` dictionary is defined elsewhere
class Detect(Cog):
    """Detects listed words in listed channels and notifies listed users by DMing them"""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @Cog.listener()
    async def on_message(message: discord.Message) -> None:
        """Listens for a message and checks its relevant"""
        # Ignore bot messages
        if message.author.bot:
            return

        # Check if this channel has any tracked words
        channel_id = message.channel.id
        if channel_id not in channel_word_trackers:
            return

        # Get the words tracked for this channel
        tracked_words_for_channel = channel_word_trackers[channel_id]
        content_lower = message.content.lower()

        # Check each tracked word in this channel
        for word, user_ids in tracked_words_for_channel.items():
            if word in content_lower:
                if is_spam(message):
                    continue
                else:
                    # If not spam, DM all users who track this word in this channel
                    for user_id in user_ids:
                        user = bot.get_user(user_id)
                        if user is None:
                            try:
                                user = await bot.fetch_user(user_id)
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