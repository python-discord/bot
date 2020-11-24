import asyncio
import unittest

from async_rediscache import RedisSession

from bot.constants import TIME_FORMATS, Roles
from bot.exts.moderation.stream import Stream
from tests.helpers import MockBot, MockRole, MockMember

redis_session = None
redis_loop = asyncio.get_event_loop()


def setUpModule():  # noqa: N802
    """Create and connect to the fakeredis session."""
    global redis_session
    redis_session = RedisSession(use_fakeredis=True)
    redis_loop.run_until_complete(redis_session.connect())


def tearDownModule():  # noqa: N802
    """Close the fakeredis session."""
    if redis_session:
        redis_loop.run_until_complete(redis_session.close())


class StreamCommandTest(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Stream(self.bot)

    def test_linking_time_format_from_alias_or_key(self):
        """
        User provided time format needs to be lined to a proper entry in TIME_FORMATS
        This Test checks _link_from_alias method
        Checking for whether alias or key exists in TIME_FORMATS is done before calling this function
        """
        FORMATS = []
        for key, entry in TIME_FORMATS.items():
            FORMATS.extend(entry["aliases"])
            FORMATS.append(key)

        test_cases = (("sec", "second"),
                      ("s", "second"),
                      ("seconds", "second"),
                      ("second", "second"),
                      ("secs", "second"),
                      ("min", "minute"),
                      ("m", "minute"),
                      ("minutes", "minute"),
                      ("hr", "hour"),
                      ("hrs", "hour"),
                      ("hours", "hour"),
                      ("d", "day"),
                      ("days", "day"),
                      ("yr", "year"),
                      ("yrs", "year"),
                      ("y", "year"))

        for case in test_cases:
            linked = self.cog._link_from_alias(case[0])[1]
            self.assertEqual(linked, case[1])

    def test_parsing_duration_and_time_format_to_seconds(self):
        """
        Test calculating time in seconds from duration and time unit
        This test is technically dependent on _link_from_alias function, not the best practice but necessary
        """
        test_cases = ((1, "minute", 60), (5, "second", 5), (2, "day", 172800))
        for case in test_cases:
            time_in_seconds = self.cog._parse_time_to_seconds(case[0], case[1])
            self.assertEqual(time_in_seconds, case[2])

    def test_checking_if_user_has_streaming_permission(self):
        """
        Test searching for video role in Member.roles
        """
        user1 = MockMember(roles=[MockRole(id=Roles.video)])
        user2 = MockMember()
        already_allowed_user1 = any(Roles.video == role.id for role in user1.roles)
        self.assertEqual(already_allowed_user1, True)

        already_allowed_user2 = any(Roles.video == role.id for role in user2.roles)
        self.assertEqual(already_allowed_user2, False)
