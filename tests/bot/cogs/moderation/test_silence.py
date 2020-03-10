import asyncio
import unittest
from unittest import mock

from bot.cogs.moderation.silence import FirstHash, Silence
from bot.constants import Emojis
from tests.helpers import MockBot, MockContext


class FirstHashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_cases = (
            (FirstHash(0, 4), FirstHash(0, 5)),
            (FirstHash("string", None), FirstHash("string", True))
        )

    def test_hashes_equal(self):
        """Check hashes equal with same first item."""

        for tuple1, tuple2 in self.test_cases:
            with self.subTest(tuple1=tuple1, tuple2=tuple2):
                self.assertEqual(hash(tuple1), hash(tuple2))

    def test_eq(self):
        """Check objects are equal with same first item."""

        for tuple1, tuple2 in self.test_cases:
            with self.subTest(tuple1=tuple1, tuple2=tuple2):
                self.assertTrue(tuple1 == tuple2)


class SilenceTests(unittest.TestCase):
    def setUp(self) -> None:

        self.bot = MockBot()
        self.cog = Silence(self.bot)
        self.ctx = MockContext()

    def test_silence_sent_correct_discord_message(self):
        """Check if proper message was sent when called with duration in channel with previous state."""
        test_cases = (
            (0.0001, f"{Emojis.check_mark} #channel silenced for 0.0001 minute(s).", True,),
            (None, f"{Emojis.check_mark} #channel silenced indefinitely.", True,),
            (5, f"{Emojis.cross_mark} #channel is already silenced.", False,),
        )
        for duration, result_message, _silence_patch_return in test_cases:
            with self.subTest(
                    silence_duration=duration,
                    result_message=result_message,
                    starting_unsilenced_state=_silence_patch_return
            ):
                with mock.patch.object(self.cog, "_silence", return_value=_silence_patch_return):
                    asyncio.run(self.cog.silence.callback(self.cog, self.ctx, duration))
                    self.ctx.send.call_args.assert_called_once_with(result_message)

    def test_unsilence_sent_correct_discord_message(self):
        """Check if proper message was sent to `alert_chanel`."""
        with mock.patch.object(self.cog, "_unsilence", return_value=True):
            asyncio.run(self.cog.unsilence.callback(self.cog, self.ctx))
            self.ctx.channel.send.call_args.assert_called_once_with(f"{Emojis.check_mark} Unsilenced #channel.")
