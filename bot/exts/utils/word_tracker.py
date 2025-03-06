from discord.ext import commands
from discord.ext.commands import Context
import json
from pathlib import Path

from bot.bot import Bot
from bot.log import get_logger

log = get_logger(__name__)

class WordTracker(commands.Cog):
    """Cog for storing word tracking information."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.json_path = Path("/tmp/word_trackers.json")
        log.info("WordTracker cog loaded!")

    def read_json(self) -> dict:
        """Read the JSON file."""
        if not self.json_path.exists():
            return {}
        try:
            return json.loads(self.json_path.read_text())
        except Exception as e:
            log.error(f"Failed to read JSON: {e}")
            return {}

    def write_json(self, data: dict) -> None:
        """Write to the JSON file."""
        try:
            self.json_path.parent.mkdir(exist_ok=True)
            self.json_path.write_text(json.dumps(data, indent=4))
        except Exception as e:
            log.error(f"Failed to write JSON: {e}")

    @commands.command(name="track")
    async def track_word(self, ctx: Context, word: str) -> None:
        """Store tracking information for a word in the current channel."""
        data = self.read_json()
        channel_id = str(ctx.channel.id)
        user_id = ctx.author.id

        if channel_id not in data:
            data[channel_id] = {}
        if word not in data[channel_id]:
            data[channel_id][word] = []
        if user_id not in data[channel_id][word]:
            data[channel_id][word].append(user_id)

        self.write_json(data)
        await ctx.send(f"I will now track the word '{word}' in this channel!")

    @commands.command(name="tracked")
    async def show_tracked(self, ctx: Context) -> None:
        """Show all tracked words in the current channel."""
        data = self.read_json()
        channel_id = str(ctx.channel.id)

        if channel_id not in data or not data[channel_id]:
            await ctx.send("No words are being tracked in this channel.")
            return

        message = "**Tracked words in this channel:**\n"
        for word, user_ids in data[channel_id].items():
            users = [f"<@{user_id}>" for user_id in user_ids]
            message += f"\n• '{word}' tracked by: {', '.join(users)}"

        await ctx.send(message)

    @commands.command(name="untrack")
    async def untrack_word(self, ctx: Context, word: str) -> None:
        """Stop tracking a word in the current channel."""
        data = self.read_json()
        channel_id = str(ctx.channel.id)
        user_id = ctx.author.id

        if channel_id not in data or word not in data[channel_id]:
            await ctx.send(f"The word '{word}' is not being tracked in this channel.")
            return

        if user_id in data[channel_id][word]:
            data[channel_id][word].remove(user_id)
            
            # Clean up empty entries
            if not data[channel_id][word]:
                del data[channel_id][word]
            if not data[channel_id]:
                del data[channel_id]

            self.write_json(data)
            await ctx.send(f"Stopped tracking the word '{word}' in this channel!")
        else:
            await ctx.send(f"You are not tracking the word '{word}' in this channel.")

async def setup(bot: Bot) -> None:
    """Load the WordTracker cog."""
    await bot.add_cog(WordTracker(bot))