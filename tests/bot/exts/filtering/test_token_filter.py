import unittest

import arrow

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.token import TokenFilter
from tests.helpers import MockMember, MockMessage, MockTextChannel


class TokenFilterTests(unittest.IsolatedAsyncioTestCase):
    """Test functionality of the token filter."""

    def setUp(self) -> None:
        member = MockMember(id=123)
        channel = MockTextChannel(id=345)
        message = MockMessage(author=member, channel=channel)
        self.ctx = FilterContext(Event.MESSAGE, member, channel, "", message)

    async def test_token_filter_triggers(self):
        """The filter should evaluate to True only if its token is found in the context content."""
        test_cases = (
            (r"hi", "oh hi there", True),
            (r"hi", "goodbye", False),
            (r"bla\d{2,4}", "bla18", True),
            (r"bla\d{2,4}", "bla1", False),
            # See advisory https://github.com/python-discord/bot/security/advisories/GHSA-j8c3-8x46-8pp6
            (r"TOKEN", "https://google.com TOKEN", True),
            (r"TOKEN", "https://google.com something else", False)
        )
        now = arrow.utcnow().timestamp()

        for pattern, content, expected in test_cases:
            with self.subTest(
                pattern=pattern,
                content=content,
                expected=expected,
            ):
                filter_ = TokenFilter({
                    "id": 1,
                    "content": pattern,
                    "description": None,
                    "settings": {},
                    "additional_settings": {},
                    "created_at": now,
                    "updated_at": now
                })
                self.ctx.content = content
                result = await filter_.triggered_on(self.ctx)
                self.assertEqual(result, expected)
