import unittest
from bot.constants import TIME_FORMATS
from bot.exts.moderation.stream import Stream
from tests.helpers import MockContext, MockBot


class StreamCommandTest(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Stream(self.bot)
        self.ctx = MockContext()

    def test_linking_time_format_from_alias_or_key(self):
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
        test_cases = ((1, "minute", 60), (5, "second", 5), (2, "day", 172800))
        for case in test_cases:
            time_in_seconds = self.cog._parse_time_to_seconds(case[0], case[1])
            self.assertEqual(time_in_seconds, case[2])
