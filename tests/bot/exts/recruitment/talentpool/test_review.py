import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from bot.exts.recruitment.talentpool import _review
from tests.helpers import MockBot, MockMember, MockMessage, MockReaction, MockTextChannel


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


def nomination(
    inserted_at: datetime,
    num_entries: int,
    reviewed: bool = False,
    id: int | None = None,
    msg_count: int = 1000,
) -> Mock:
    id = id or MockMember().id
    return Mock(
        id=id or MockMember().id,
        user_id=id,
        inserted_at=inserted_at,
        entries=[Mock() for _ in range(num_entries)],
        reviewed=reviewed,
        _msg_count=msg_count,
    )


class ReviewerTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the talentpool reviewer."""

    def setUp(self):
        self.bot_user = MockMember(bot=True)
        self.bot = MockBot(user=self.bot_user)

        self.voting_channel = MockTextChannel()
        self.bot.get_channel = Mock(return_value=self.voting_channel)

        self.nomination_api = Mock(name="MockNominationAPI")
        self.reviewer = _review.Reviewer(self.bot, self.nomination_api)

    @patch("bot.exts.recruitment.talentpool._review.MAX_ONGOING_REVIEWS", 3)
    @patch("bot.exts.recruitment.talentpool._review.MIN_REVIEW_INTERVAL", timedelta(days=1))
    async def test_is_ready_for_review(self):
        """Tests for the `is_ready_for_review` function."""
        too_recent = datetime.now(UTC) - timedelta(hours=1)
        not_too_recent = datetime.now(UTC) - timedelta(days=7)
        ticket_reaction = MockReaction(users=[self.bot_user], emoji="\N{TICKET}")

        cases = (
            # Only one active review, and not too recent, so ready.
            (
                [
                    MockMessage(author=self.bot_user, content="wookie for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Not a review", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Not a review", created_at=not_too_recent),
                ],
                not_too_recent.timestamp(),
                True,
            ),

            # Three active reviews, so not ready.
            (
                [
                    MockMessage(author=self.bot_user, content="Chrisjl for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Zig for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Scaleios for Helper!", created_at=not_too_recent),
                ],
                not_too_recent.timestamp(),
                False,
            ),

            # Only one active review, but too recent, so not ready.
            (
                [
                    MockMessage(author=self.bot_user, content="Chrisjl for Helper!", created_at=too_recent),
                ],
                too_recent.timestamp(),
                False,
            ),

            # Only two active reviews, and not too recent, so ready.
            (
                [
                    MockMessage(author=self.bot_user, content="Not a review", created_at=too_recent),
                    MockMessage(author=self.bot_user, content="wookie for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="wookie for Helper!", created_at=not_too_recent),
                    MockMessage(author=self.bot_user, content="Not a review", created_at=not_too_recent),
                ],
                not_too_recent.timestamp(),
                True,
            ),

            # Over the active threshold, but below the total threshold
            (
                [
                    MockMessage(
                        author=self.bot_user,
                        content="joe for Helper!",
                        created_at=not_too_recent,
                        reactions=[ticket_reaction]
                    )
                ] * 6,
                not_too_recent.timestamp(),
                True
            ),

            # Over the total threshold
            (
                [
                    MockMessage(
                        author=self.bot_user,
                        content="joe for Helper!",
                        created_at=not_too_recent,
                        reactions=[ticket_reaction]
                    )
                ] * 11,
                not_too_recent.timestamp(),
                False
            ),

            # No messages, so ready.
            ([], None, True),
        )

        for messages, last_review_timestamp, expected in cases:
            with self.subTest(messages=messages, expected=expected):
                self.voting_channel.history = AsyncIterator(messages)

                cache_get_mock = AsyncMock(return_value=last_review_timestamp)
                self.reviewer.status_cache.get = cache_get_mock

                res = await self.reviewer.is_ready_for_review()

                self.assertIs(res, expected)
                cache_get_mock.assert_called_with("last_vote_date")

    @patch("bot.exts.recruitment.talentpool._review.MIN_NOMINATION_TIME", timedelta(days=7))
    async def test_get_nomination_to_review(self):
        """Test get_nomination_to_review function."""
        now = datetime.now(UTC)

        # Each case contains a list of nominations, followed by the index in that list
        # of the one that should be selected, or None if None should be returned
        cases = [
            # Don't send if too recent, already reviewed, or no recent messages.
            (
                [
                    nomination(now - timedelta(days=1), 5),
                    nomination(now - timedelta(days=10), 5, reviewed=True),
                    nomination(now - timedelta(days=10), 5, msg_count=0),

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

        for (case_num, (nominations, expected)) in enumerate(cases, 1):
            with self.subTest(case_num=case_num):
                get_nominations_mock = AsyncMock(return_value=nominations)
                self.nomination_api.get_nominations = get_nominations_mock

                activity = {nomination.id: nomination._msg_count for nomination in nominations}
                get_activity_mock = AsyncMock(return_value=activity)
                self.nomination_api.get_activity = get_activity_mock

                res = await self.reviewer.get_nomination_to_review()

                if expected is None:
                    self.assertIsNone(res)
                else:
                    self.assertEqual(res, nominations[expected])
                get_nominations_mock.assert_called_once_with(active=True)
                get_activity_mock.assert_called_once()

    @patch("bot.exts.recruitment.talentpool._review.MIN_NOMINATION_TIME", timedelta(days=0))
    async def test_get_nomination_to_review_order(self):
        now = datetime.now(UTC)

        # Each case in cases is a list of nominations in the order they should be chosen from first to last
        cases = [
            [
                nomination(now - timedelta(days=10), 3, id=1),
                nomination(now - timedelta(days=50), 2, id=2),
                nomination(now - timedelta(days=100), 1, id=3),
            ],
            [
                nomination(now - timedelta(days=100), 2, id=1),
                nomination(now - timedelta(days=10), 3, id=2),
                nomination(now - timedelta(days=80), 1, id=3),
                nomination(now - timedelta(days=79), 1, id=4),
                nomination(now - timedelta(days=10), 2, id=5),
            ],
            [
                nomination(now - timedelta(days=200), 8, id=1),
                nomination(now - timedelta(days=359), 4, id=2),
                nomination(now - timedelta(days=230), 5, id=3),
                nomination(now - timedelta(days=331), 3, id=4),
                nomination(now - timedelta(days=113), 5, id=5),
                nomination(now - timedelta(days=186), 3, id=6),
                nomination(now - timedelta(days=272), 2, id=7),
                nomination(now - timedelta(days=30), 4, id=8),
                nomination(now - timedelta(days=198), 2, id=9),
                nomination(now - timedelta(days=270), 1, id=10),
                nomination(now - timedelta(days=140), 1, id=11),
                nomination(now - timedelta(days=19), 2, id=12),
                nomination(now - timedelta(days=30), 1, id=13),
            ]
        ]

        for case_num, case in enumerate(cases, 1):
            with self.subTest(case_num=case_num):
                for i in range(len(case)):
                    with self.subTest(nomination_num=i+1):
                        get_nominations_mock = AsyncMock(return_value=case[i:])
                        self.nomination_api.get_nominations = get_nominations_mock

                        activity = {nomination.id: nomination._msg_count for nomination in case}
                        get_activity_mock = AsyncMock(return_value=activity)
                        self.nomination_api.get_activity = get_activity_mock

                        res = await self.reviewer.get_nomination_to_review()
                        self.assertEqual(res, case[i])
                        get_nominations_mock.assert_called_once_with(active=True)
