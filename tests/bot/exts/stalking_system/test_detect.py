import json
import unittest
from unittest.mock import AsyncMock, patch, Mock, MagicMock
import discord
from pathlib import Path
from bot.bot import Bot
from bot.exts.stalking_system.detect import send_dm, Detect


class TestSend_DM(unittest.IsolatedAsyncioTestCase):

    async def test_send_dm_success(self):
        """Test if send_dm successfully sends a message"""
        mock_user = AsyncMock()

        await send_dm(mock_user, "Hello!")

        mock_user.send.assert_awaited_once_with("Hello!")

    async def test_send_dm_user_not_found(self):
        """Test handling of discord.NotFound"""
        mock_user = AsyncMock()
        mock_user.send.side_effect = discord.NotFound(Mock(), "User not found")

        with patch("builtins.print") as mock_print:
            await send_dm(mock_user, "Hello!")
            mock_print.assert_called_once_with("User not found.")

    async def test_send_dm_forbidden(self):
        """Test handling of discord.Forbidden"""
        mock_user = AsyncMock()
        mock_user.send.side_effect = discord.Forbidden(Mock(), "Permission denied")

        with patch("builtins.print") as mock_print:
            await send_dm(mock_user, "Hello!")
            mock_print.assert_called_once_with("Permission denied.")

    async def test_send_dm_http_exception(self):
        """Test handling of discord.HTTPException"""
        mock_user = AsyncMock()
        mock_user.send.side_effect = discord.HTTPException(Mock(), "HTTP Error")

        with patch("builtins.print") as mock_print:
            await send_dm(mock_user, "Hello!")
            mock_print.assert_called_once_with("Failed to send DM: HTTP Error")








class TestDetect(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Set up the Detect cog with a mock bot so that we can test our function"""
        self.mock_bot = MagicMock(spec=Bot)
        self.detect_cog = Detect(self.mock_bot)

        self.detect_cog.channel_word_trackers = {
                "12345": {
                    "wow": [1111]
                }
            }
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = json.dumps({
            "12345": {"wow": [1111]}
        })

        self.detect_cog.json_path = mock_path

        # Replace the RateLimiter methods with mocks.
        self.detect_cog.limiter.is_malicious = MagicMock(return_value=False)
        self.detect_cog.limiter.record_trigger = MagicMock()

    async def test_ignore_bot_message(self):
        """Test that messages from bots are ignored."""
        message = MagicMock(spec=discord.Message)
        message.author.bot = True
        await self.detect_cog.on_message(message)

        # Assert: No user lookup should be performed.
        self.mock_bot.get_user.assert_not_called()

    async def test_no_tracked_channel(self):
        """Test that if the channel is not tracked, nothing happens."""
        message = MagicMock(spec=discord.Message)
        message.author.bot = False
        message.channel.id = 9999
        message.content = "wow"
        await self.detect_cog.on_message(message)

        self.mock_bot.get_user.assert_not_called()



    async def test_spam_blocked(self):
        """Test that if the RateLimiter considers the message spam, no DM is sent."""
        # Configure the limiter to mark the message as malicious.
        self.detect_cog.limiter.is_malicious = MagicMock(return_value=True)

        message = MagicMock(spec=discord.Message)
        message.author.bot = False
        message.author.id = 2222
        message.channel.id = 12345
        message.content = "wow"
        await self.detect_cog.on_message(message)

        self.mock_bot.get_user.assert_not_called()


if __name__ == '__main__':
    unittest.main()