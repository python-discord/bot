import unittest

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.token import TokenFilter
from tests.helpers import MockMember, MockMessage, MockTextChannel


class FilterTests(unittest.TestCase):
    """Test functionality of the token filter."""

    def setUp(self) -> None:
        member = MockMember(id=123)
        channel = MockTextChannel(id=345)
        message = MockMessage(author=member, channel=channel)
        self.ctx = FilterContext(Event.MESSAGE, member, channel, "", message)

    def test_token_filter_triggers(self):
        """The filter should evaluate to True only if its token is found in the context content."""
        test_cases = (
            (r"hi", "oh hi there", True),
            (r"hi", "goodbye", False),
            (r"bla\d{2,4}", "bla18", True),
            (r"bla\d{2,4}", "bla1", False)
        )

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
                    "additional_field": "{}"  # noqa: P103
                })
                self.ctx.content = content
                result = filter_.triggered_on(self.ctx)
                self.assertEqual(result, expected)
