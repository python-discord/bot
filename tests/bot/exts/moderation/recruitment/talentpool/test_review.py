import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from bot.exts.recruitment.talentpool import _review
from tests.helpers import MockBot, MockMember, MockMessage, MockTextChannel


class AsyncIterator:
    """Normal->Async iterator helper."""

    def __init__(self, seq):
        self.iter = iter(seq)

    def __aiter__(self):
        return self

    # Allows it to be used to mock the discord TextChannel.history function
    def __call__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.iter)
        except StopIteration:
            raise StopAsyncIteration


def nomination(inserted_at, num_entries, reviewed=False):
    return (
        MockMember().id,
        {"inserted_at": inserted_at.isoformat(), "entries": [Mock() for _ in range(num_entries)], "reviewed": reviewed},
    )


class ReviewerTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the talentpool reviewer."""

    def setUp(self):
        self.bot_user = MockMember(bot=True)
        self.bot = MockBot(user=self.bot_user)

        self.voting_channel = MockTextChannel()
        self.bot.get_channel = Mock(return_value=self.voting_channel)

        self.pool = Mock(name="MockTalentPool")
        self.reviewer = _review.Reviewer(self.bot, self.pool)

    @patch("bot.exts.recruitment.talentpool._review.MAX_ONGOING_REVIEWS", 3)
    @patch("bot.exts.recruitment.talentpool._review.MIN_REVIEW_INTERVAL", timedelta(days=1))
    async def test_is_ready_for_review(self):
        """Tests for the `is_ready_for_review` function."""
        too_recent = datetime.now(timezone.utc) - timedelta(hours=1)
        not_too_recent = datetime.now(timezone.utc) - timedelta(days=7)
        cases = (
            # Only one review, and not too recent, so ready.
            (
                [
                    MockMessage(author=self.bot_user, content="wookie for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Not a review", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Not a review", created_at=not_too_recent),
                ],
                True,
            ),

            # Three reviews, so not ready.
            (
                [
                    MockMessage(author=self.bot_user, content="Chrisjl for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Zig for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Scaleios for Helper!", created_at=not_too_recent),
                ],
                False,
            ),

            # Only one review, but too recent, so not ready.
            (
                [
                    MockMessage(author=self.bot_user, content="Chrisjl for Helper!", created_at=too_recent),
                ],
                False,
            ),

            # Only two reviews, and not too recent, so ready.
            (
                [
                    MockMessage(author=self.bot_user, content="Not a review", created_at=too_recent),
                    MockMessage(author=self.bot_user, content="wookie for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="wookie for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Not a review", created_at=not_too_recent),
                ],
                True,
            ),

            # No messages, so ready.
            ([], True),
        )

        for messages, expected in cases:
            with self.subTest(messages=messages, expected=expected):
                self.voting_channel.history = AsyncIterator(messages)
                res = await self.reviewer.is_ready_for_review()
                self.assertIs(res, expected)

    @patch("bot.exts.recruitment.talentpool._review.MIN_NOMINATION_TIME", timedelta(days=7))
    async def test_get_user_for_review(self):
        """Test get_user_for_review function."""
        now = datetime.now(timezone.utc)

        # Each case contains a list of nominations, followed by the index in that list
        # of the one that should be selected, or None if None should be returned
        cases = [
            # One nomination, too recent so don't send.
            (
                [
                    nomination(now - timedelta(days=1), 5),
                ],
                None,
            ),

            # First one has most entries so should be returned.
            (
                [
                    nomination(now - timedelta(days=10), 6),
                    nomination(now - timedelta(days=10), 5),
                    nomination(now - timedelta(days=9), 5),
                    nomination(now - timedelta(days=11), 5),
                ],
                0,
            ),

            # Same number of entries so oldest (second) should be returned.
            (
                [
                    nomination(now - timedelta(days=1), 2),
                    nomination(now - timedelta(days=80), 2),
                    nomination(now - timedelta(days=79), 2),
                ],
                1,
            ),
        ]

        for nominations, expected in cases:
            nomination_dict = dict(nominations)

            with self.subTest(nominations=nominations, expected=expected):
                self.pool.cache = nomination_dict
                res = await self.reviewer.get_user_for_review()

                if expected is None:
                    self.assertIsNone(res)
                else:
                    self.assertEqual(res, nominations[expected][0])
