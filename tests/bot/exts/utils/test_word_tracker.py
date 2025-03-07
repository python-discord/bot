import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from bot.exts.utils.word_tracker import WordTracker
from tests.helpers import MockBot, MockContext, MockTextChannel



class WordTrackerTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the WordTracker cog."""

    def setUp(self):
        """Set up fresh objects for each test."""
        self.bot = MockBot()
        self.cog = WordTracker(self.bot)
        self.ctx = MockContext()
        self.ctx.channel = MockTextChannel(id=123)
        self.ctx.author.id = 456
        self.test_data = {
            "123": {  # Channel ID
                "test_word": [456]  # User ID
            }
        }

        self.fake_file = ['{}']
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.write_text.side_effect = lambda text: self.fake_file.__setitem__(0, text)
        mock_path.read_text.side_effect = lambda: self.fake_file[0]
        self.cog.json_path = mock_path


    def tearDown(self):
        """Clean up after each test."""
        # Clear any stored data
        self.cog.write_json({})

    async def test_track_word_in_new_channel(self):
        """Words should be trackable in a new channel."""
        test_word = "hello"
        await self.cog.track_word(self.cog, self.ctx, test_word)

        stored_data = self.cog.read_json()
        channel_id = str(self.ctx.channel.id)

        self.assertIn(channel_id, stored_data)
        self.assertIn(test_word, stored_data[channel_id])
        self.assertIn(self.ctx.author.id, stored_data[channel_id][test_word])

    async def test_track_word_in_existing_channel(self):
        """Words should be trackable in a channel that already has tracked words."""
        self.cog.write_json(self.test_data)
        new_word = "new_word"

        await self.cog.track_word(self.cog, self.ctx, new_word)

        stored_data = self.cog.read_json()
        channel_id = str(self.ctx.channel.id)

        self.assertIn(new_word, stored_data[channel_id])
        self.assertIn("test_word", stored_data[channel_id])

    async def test_untrack_existing_word(self):
        """Users should be able to untrack words they're tracking."""
        self.cog.write_json(self.test_data)
        word_to_untrack = "test_word"

        await self.cog.untrack_word(self.cog, self.ctx, word_to_untrack)

        stored_data = self.cog.read_json()
        channel_data = stored_data.get(str(self.ctx.channel.id), {})
        self.assertNotIn(word_to_untrack, channel_data)

    async def test_untrack_nonexistent_word(self):
        """Attempting to untrack a non-tracked word should not modify the data."""
        self.cog.write_json(self.test_data)
        initial_data = self.cog.read_json()

        await self.cog.untrack_word(self.cog, self.ctx, "nonexistent_word")

        final_data = self.cog.read_json()
        self.assertEqual(initial_data, final_data)

    async def test_show_tracked_words_empty_channel(self):
        """Showing tracked words in an empty channel should display appropriate message."""
        self.ctx.send = AsyncMock()

        await self.cog.show_tracked(self.cog, self.ctx)

        self.ctx.send.assert_called_once_with(
            "No words are being tracked in this channel."
        )

    async def test_show_tracked_words_with_data(self):
        """Showing tracked words should display all tracked words and their trackers."""
        self.cog.write_json(self.test_data)
        self.ctx.send = AsyncMock()

        await self.cog.show_tracked(self.cog, self.ctx)

        expected_message = "**Tracked words in this channel:**\n\n• 'test_word' tracked by: <@456>"
        self.ctx.send.assert_called_once_with(expected_message)

    def test_read_json_empty_file(self):
        """Reading from an empty JSON file should return an empty dict."""
        self.cog.write_json({})
        data = self.cog.read_json()
        self.assertEqual(data, {})

    def test_write_and_read_json_persistence(self):
        """Data should persist correctly when written and read back."""
        self.cog.write_json(self.test_data)
        read_data = self.cog.read_json()
        self.assertEqual(read_data, self.test_data)

    @patch("bot.exts.utils.word_tracker.Path")
    def test_write_json_handles_errors(self, mock_path):
        """JSON write errors should be handled gracefully."""
        mock_path.return_value.write_text.side_effect = Exception("Test error")
        try:
            self.cog.write_json(self.test_data)
        except Exception as e:
            self.fail(f"write_json raised an exception: {e}")

async def setup(bot: MockBot) -> None:
    """Load the WordTracker cog."""
    await bot.add_cog(WordTracker(bot))
