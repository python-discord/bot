import unittest

import arrow

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.antispam.emoji import DISCORD_EMOJI_RE, EmojiFilter
from tests.helpers import MockMember, MockMessage, MockTextChannel

FILTER_DATA = {
    "id": 1,
    "content": "emoji",
    "description": None,
    "settings": {},
    "additional_settings": {},
    "created_at": arrow.utcnow().timestamp(),
    "updated_at": arrow.utcnow().timestamp(),
}


def make_message(content: str, author: MockMember, seconds_ago: float = 0) -> MockMessage:
    """Create a MockMessage with given content, author, and relative creation time."""
    created_at = arrow.utcnow().shift(seconds=-seconds_ago).datetime
    return MockMessage(author=author, content=content, created_at=created_at)


class EmojiFilterRegexTests(unittest.TestCase):
    """Tests for the DISCORD_EMOJI_RE regex pattern."""

    def test_standard_custom_emoji(self):
        """Standard Discord custom emoji like <:name:id> should be matched."""
        matches = DISCORD_EMOJI_RE.findall("<:lemon:123456789>")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], "<:lemon:123456789>")

    def test_animated_custom_emoji(self):
        """Animated Discord custom emoji like <a:name:id> should be matched."""
        matches = DISCORD_EMOJI_RE.findall("<a:wave:987654321>")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], "<a:wave:987654321>")

    def test_text_emoji(self):
        """Text emoji in :name: format (as produced by demojize) should be matched."""
        matches = DISCORD_EMOJI_RE.findall(":grinning_face:")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], ":grinning_face:")

    def test_multiple_emoji_types(self):
        """Multiple emoji of different types in one string should all be matched."""
        text = "<:lemon:123> <a:wave:456> :thumbs_up:"
        matches = DISCORD_EMOJI_RE.findall(text)
        self.assertEqual(len(matches), 3)

    def test_no_false_positives_in_plain_text(self):
        """Plain text without emoji syntax should not be matched."""
        matches = DISCORD_EMOJI_RE.findall("hello world, no emoji here")
        self.assertEqual(len(matches), 0)


class EmojiFilterTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the EmojiFilter antispam filter."""

    def setUp(self) -> None:
        self.member = MockMember(id=123)
        self.other_member = MockMember(id=456)
        self.channel = MockTextChannel(id=345)
        self.filter = EmojiFilter(FILTER_DATA)

    def _make_ctx(self, messages: list) -> FilterContext:
        """Create a FilterContext where ctx.content is a list of messages."""
        return FilterContext(
            Event.MESSAGE,
            self.member,
            self.channel,
            messages,
            messages[0] if messages else None,
        )

    async def test_does_not_trigger_at_or_below_threshold(self):
        """Filter should not trigger when emoji count is at or below the threshold."""
        # Default threshold is 20; use 5 messages each with 4 emojis = 20 total (not exceeding)
        messages = [
            make_message("<:a:1> <:b:2> <:c:3> <:d:4>", self.member)
            for _ in range(5)
        ]
        ctx = self._make_ctx(messages)
        result = await self.filter.triggered_on(ctx)
        self.assertFalse(result)

    async def test_triggers_above_threshold(self):
        """Filter should trigger when emoji count exceeds the threshold."""
        # Default threshold is 20; use 3 messages each with 8 emojis = 24 total (exceeds threshold)
        messages = [
            make_message(
                "<:a:1> <:b:2> <:c:3> <:d:4> <:e:5> <:f:6> <:g:7> <:h:8>",
                self.member,
            )
            for _ in range(3)
        ]
        ctx = self._make_ctx(messages)
        result = await self.filter.triggered_on(ctx)
        self.assertTrue(result)

    async def test_counts_unicode_emojis(self):
        """Unicode emojis should be counted after being converted with demojize."""
        # Each '😀' gets converted to ':grinning_face:' by demojize
        # 21 unicode emojis should exceed the threshold of 20
        emoji_spam = "😀" * 21
        messages = [make_message(emoji_spam, self.member)]
        ctx = self._make_ctx(messages)
        result = await self.filter.triggered_on(ctx)
        self.assertTrue(result)

    async def test_counts_animated_emojis(self):
        """Animated Discord emojis (<a:name:id>) should be counted."""
        # 21 animated emojis should exceed the threshold of 20
        animated_spam = " ".join(f"<a:wave:{i}>" for i in range(21))
        messages = [make_message(animated_spam, self.member)]
        ctx = self._make_ctx(messages)
        result = await self.filter.triggered_on(ctx)
        self.assertTrue(result)

    async def test_excludes_code_blocks(self):
        """Emojis inside code blocks should not be counted."""
        # 21 emojis inside a code block should NOT trigger the filter
        code_block = "```\n" + "<:a:1> " * 21 + "\n```"
        messages = [make_message(code_block, self.member)]
        ctx = self._make_ctx(messages)
        result = await self.filter.triggered_on(ctx)
        self.assertFalse(result)

    async def test_only_counts_messages_from_ctx_author(self):
        """Only messages from the context's author should be counted, not other users."""
        # Author sends 5 emojis, other_member sends 30 emojis - should not trigger for author
        author_messages = [make_message("<:a:1> <:b:2> <:c:3> <:d:4> <:e:5>", self.member)]
        other_messages = [make_message("<:x:1> " * 30, self.other_member)]
        all_messages = author_messages + other_messages
        ctx = self._make_ctx(all_messages)
        result = await self.filter.triggered_on(ctx)
        self.assertFalse(result)

    async def test_only_counts_messages_within_interval(self):
        """Messages outside the time interval should not be counted."""
        # Default interval is 10 seconds; send 30 emojis but 11 seconds ago
        old_messages = [make_message("<:a:1> " * 30, self.member, seconds_ago=11)]
        recent_messages = [make_message("<:a:1>", self.member, seconds_ago=1)]
        # old_messages won't be in the takewhile loop since they're older than interval
        # The messages list needs to be newest-first (as MessageCache provides)
        all_messages = recent_messages + old_messages
        ctx = self._make_ctx(all_messages)
        result = await self.filter.triggered_on(ctx)
        self.assertFalse(result)

    async def test_filter_info_set_on_trigger(self):
        """When triggered, filter_info should contain the emoji count."""
        messages = [
            make_message("<:a:1> " * 21, self.member)
        ]
        ctx = self._make_ctx(messages)
        await self.filter.triggered_on(ctx)
        self.assertIn(self.filter, ctx.filter_info)
        self.assertIn("21", ctx.filter_info[self.filter])

    async def test_related_messages_populated_on_trigger(self):
        """When triggered, ctx.related_messages should include the offending messages."""
        messages = [make_message("<:a:1> " * 21, self.member)]
        ctx = self._make_ctx(messages)
        await self.filter.triggered_on(ctx)
        self.assertGreater(len(ctx.related_messages), 0)
