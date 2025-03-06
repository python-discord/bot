from discord.ext import commands
from discord.ext.commands import Context

from bot.bot import Bot
from bot.log import get_logger

log = get_logger(__name__)

class WordTracker(commands.Cog):
    """Cog for storing word tracking information."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.channel_word_trackers: dict[int, dict[str, set[int]]] = {}
        log.info("WordTracker cog loaded!")

    @commands.command(name="track")
    async def track_word(self, ctx: Context, word: str) -> None:
        """
        Store tracking information for a word in the current channel.

        Args:
            word: The word to track
        """
        log.info(f"Track command called by {ctx.author} in {ctx.channel} with word: {word}")

        # Initialize channel tracking if not exists
        if ctx.channel.id not in self.channel_word_trackers:
            self.channel_word_trackers[ctx.channel.id] = {}

        # Initialize word tracking if not exists
        if word not in self.channel_word_trackers[ctx.channel.id]:
            self.channel_word_trackers[ctx.channel.id][word] = set()

        # Add user to tracking set
        self.channel_word_trackers[ctx.channel.id][word].add(ctx.author.id)

        await ctx.send(f"I will now track the word '{word}' in this channel!")

    @commands.command(name="tracked")
    async def show_tracked(self, ctx: Context) -> None:
        """Show all tracked words in the current channel."""
        if ctx.channel.id not in self.channel_word_trackers:
            await ctx.send("No words are being tracked in this channel.")
            return

        tracked_words = self.channel_word_trackers[ctx.channel.id]
        if not tracked_words:
            await ctx.send("No words are being tracked in this channel.")
            return

        message = "**Tracked words in this channel:**\n"
        for word, user_ids in tracked_words.items():
            users = [f"<@{user_id}>" for user_id in user_ids]
            message += f"\n• '{word}' tracked by: {', '.join(users)}"

        await ctx.send(message)

    @commands.command(name="untrack")
    async def untrack_word(self, ctx: Context, word: str) -> None:
        """
        Stop tracking a word in the current channel.

        Args:
            word: The word to stop tracking
        """
        if ctx.channel.id not in self.channel_word_trackers:
            await ctx.send("No words are being tracked in this channel.")
            return

        if word not in self.channel_word_trackers[ctx.channel.id]:
            await ctx.send(f"The word '{word}' is not being tracked in this channel.")
            return

        # Remove user from tracking set
        self.channel_word_trackers[ctx.channel.id][word].discard(ctx.author.id)

        # Clean up empty sets and dictionaries
        if not self.channel_word_trackers[ctx.channel.id][word]:
            del self.channel_word_trackers[ctx.channel.id][word]
        if not self.channel_word_trackers[ctx.channel.id]:
            del self.channel_word_trackers[ctx.channel.id]

        await ctx.send(f"Stopped tracking the word '{word}' in this channel!")

async def setup(bot: Bot) -> None:
    """Load the WordTracker cog."""
    await bot.add_cog(WordTracker(bot))
