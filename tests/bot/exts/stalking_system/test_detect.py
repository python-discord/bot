import unittest
from unittest.mock import AsyncMock, patch, Mock
import discord

from bot.exts.stalking_system.detect import send_dm


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
