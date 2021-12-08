import unittest
from unittest.mock import patch

from bot.exts.filters import filtering
from tests.helpers import MockBot, autospec


class FilteringCogTests(unittest.IsolatedAsyncioTestCase):
    """Tests the `Filtering` cog."""

    def setUp(self):
        """Instantiate the bot and cog."""
        self.bot = MockBot()
        with patch("bot.utils.scheduling.create_task", new=lambda task, **_: task.close()):
            self.cog = filtering.Filtering(self.bot)

    @autospec(filtering.Filtering, "_get_filterlist_items", pass_mocks=False, return_value=["TOKEN"])
    async def test_token_filter(self):
        """Ensure that a filter token is correctly detected in a message."""
        messages = {
            "": False,
            "no matches": False,
            "TOKEN": True,

            # See advisory https://github.com/python-discord/bot/security/advisories/GHSA-j8c3-8x46-8pp6
            "https://google.com TOKEN": True,
            "https://google.com something else": False,
        }

        for message, match in messages.items():
            with self.subTest(input=message, match=match):
                result, _ = await self.cog._has_watch_regex_match(message)

                self.assertEqual(
                    match,
                    bool(result),
                    msg=f"Hit was {'expected' if match else 'not expected'} for this input."
                )
                if result:
                    self.assertEqual("TOKEN", result.group())
