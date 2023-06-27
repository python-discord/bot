import re
import unittest
from datetime import MAXYEAR, UTC, datetime
from unittest.mock import MagicMock, patch

from dateutil.relativedelta import relativedelta
from discord.ext.commands import BadArgument

from bot.converters import Duration, HushDurationConverter, ISODateTime, PackageName


class ConverterTests(unittest.IsolatedAsyncioTestCase):
    """Tests our custom argument converters."""

    @classmethod
    def setUpClass(cls):
        cls.context = MagicMock
        cls.context.author = "bob"

        cls.fixed_utc_now = datetime.fromisoformat("2019-01-01T00:00:00+00:00")

    async def test_package_name_for_valid(self):
        """PackageName returns valid package names unchanged."""
        test_values = ("foo", "le_mon", "num83r")

        for name in test_values:
            with self.subTest(identifier=name):
                conversion = await PackageName.convert(self.context, name)
                self.assertEqual(name, conversion)

    async def test_package_name_for_invalid(self):
        """PackageName raises the proper exception for invalid package names."""
        test_values = ("text_with_a_dot.", "UpperCaseName", "dashed-name")

        for name in test_values:
            with self.subTest(identifier=name), self.assertRaises(BadArgument):
                await PackageName.convert(self.context, name)

    async def test_duration_converter_for_valid(self):
        """Duration returns the correct `datetime` for valid duration strings."""
        test_values = (
            # Simple duration strings
            ("1Y", {"years": 1}),
            ("1y", {"years": 1}),
            ("1year", {"years": 1}),
            ("1years", {"years": 1}),
            ("1m", {"months": 1}),
            ("1month", {"months": 1}),
            ("1months", {"months": 1}),
            ("1w", {"weeks": 1}),
            ("1W", {"weeks": 1}),
            ("1week", {"weeks": 1}),
            ("1weeks", {"weeks": 1}),
            ("1d", {"days": 1}),
            ("1D", {"days": 1}),
            ("1day", {"days": 1}),
            ("1days", {"days": 1}),
            ("1h", {"hours": 1}),
            ("1H", {"hours": 1}),
            ("1hour", {"hours": 1}),
            ("1hours", {"hours": 1}),
            ("1M", {"minutes": 1}),
            ("1minute", {"minutes": 1}),
            ("1minutes", {"minutes": 1}),
            ("1s", {"seconds": 1}),
            ("1S", {"seconds": 1}),
            ("1second", {"seconds": 1}),
            ("1seconds", {"seconds": 1}),

            # Complex duration strings
            (
                "1y1m1w1d1H1M1S",
                {
                    "years": 1,
                    "months": 1,
                    "weeks": 1,
                    "days": 1,
                    "hours": 1,
                    "minutes": 1,
                    "seconds": 1
                }
            ),
            ("5y100S", {"years": 5, "seconds": 100}),
            ("2w28H", {"weeks": 2, "hours": 28}),

            # Duration strings with spaces
            ("1 year 2 months", {"years": 1, "months": 2}),
            ("1d 2H", {"days": 1, "hours": 2}),
            ("1 week2 days", {"weeks": 1, "days": 2}),
        )

        converter = Duration()

        for duration, duration_dict in test_values:
            expected_datetime = self.fixed_utc_now + relativedelta(**duration_dict)

            with patch("bot.converters.datetime") as mock_datetime:
                mock_datetime.now.return_value = self.fixed_utc_now

                with self.subTest(duration=duration, duration_dict=duration_dict):
                    converted_datetime = await converter.convert(self.context, duration)
                    self.assertEqual(converted_datetime, expected_datetime)

    async def test_duration_converter_for_invalid(self):
        """Duration raises the right exception for invalid duration strings."""
        test_values = (
            # Units in wrong order
            "1d1w",
            "1s1y",

            # Duplicated units
            "1 year 2 years",
            "1 M 10 minutes",

            # Unknown substrings
            "1MVes",
            "1y3breads",

            # Missing amount
            "ym",

            # Incorrect whitespace
            " 1y",
            "1S ",
            "1y  1m",

            # Garbage
            "Guido van Rossum",
            "lemon lemon lemon lemon lemon lemon lemon",
        )

        converter = Duration()

        for invalid_duration in test_values:
            with self.subTest(invalid_duration=invalid_duration):
                exception_message = f"`{invalid_duration}` is not a valid duration string."
                with self.assertRaisesRegex(BadArgument, re.escape(exception_message)):
                    await converter.convert(self.context, invalid_duration)

    @patch("bot.converters.datetime")
    async def test_duration_converter_out_of_range(self, mock_datetime):
        """Duration converter should raise BadArgument if datetime raises a ValueError."""
        mock_datetime.__add__.side_effect = ValueError
        mock_datetime.now.return_value = mock_datetime

        duration = f"{MAXYEAR}y"
        exception_message = f"`{duration}` results in a datetime outside the supported range."
        with self.assertRaisesRegex(BadArgument, re.escape(exception_message)):
            await Duration().convert(self.context, duration)

    async def test_isodatetime_converter_for_valid(self):
        """ISODateTime converter returns correct datetime for valid datetime string."""
        test_values = (
            # `YYYY-mm-ddTHH:MM:SSZ` | `YYYY-mm-dd HH:MM:SSZ`
            ("2019-09-02T02:03:05Z", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02 02:03:05Z", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),

            # `YYYY-mm-ddTHH:MM:SS±HH:MM` | `YYYY-mm-dd HH:MM:SS±HH:MM`
            ("2019-09-02T03:18:05+01:15", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02 03:18:05+01:15", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02T00:48:05-01:15", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02 00:48:05-01:15", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),

            # `YYYY-mm-ddTHH:MM:SS±HHMM` | `YYYY-mm-dd HH:MM:SS±HHMM`
            ("2019-09-02T03:18:05+0115", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02 03:18:05+0115", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02T00:48:05-0115", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02 00:48:05-0115", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),

            # `YYYY-mm-ddTHH:MM:SS±HH` | `YYYY-mm-dd HH:MM:SS±HH`
            ("2019-09-02 03:03:05+01", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02T01:03:05-01", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),

            # `YYYY-mm-ddTHH:MM:SS` | `YYYY-mm-dd HH:MM:SS`
            ("2019-09-02T02:03:05", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),
            ("2019-09-02 02:03:05", datetime(2019, 9, 2, 2, 3, 5, tzinfo=UTC)),

            # `YYYY-mm-ddTHH:MM` | `YYYY-mm-dd HH:MM`
            ("2019-11-12T09:15", datetime(2019, 11, 12, 9, 15, tzinfo=UTC)),
            ("2019-11-12 09:15", datetime(2019, 11, 12, 9, 15, tzinfo=UTC)),

            # `YYYY-mm-dd`
            ("2019-04-01", datetime(2019, 4, 1, tzinfo=UTC)),

            # `YYYY-mm`
            ("2019-02-01", datetime(2019, 2, 1, tzinfo=UTC)),

            # `YYYY`
            ("2025", datetime(2025, 1, 1, tzinfo=UTC)),
        )

        converter = ISODateTime()

        for datetime_string, expected_dt in test_values:
            with self.subTest(datetime_string=datetime_string, expected_dt=expected_dt):
                converted_dt = await converter.convert(self.context, datetime_string)
                self.assertEqual(converted_dt, expected_dt)

    async def test_isodatetime_converter_for_invalid(self):
        """ISODateTime converter raises the correct exception for invalid datetime strings."""
        test_values = (
            # Make sure it doesn't interfere with the Duration converter
            "1Y",
            "1d",
            "1H",

            # Check if it fails when only providing the optional time part
            "10:10:10",
            "10:00",

            # Invalid date format
            "19-01-01",

            # Other non-valid strings
            "fisk the tag master",
        )

        converter = ISODateTime()
        for datetime_string in test_values:
            with self.subTest(datetime_string=datetime_string):
                exception_message = f"`{datetime_string}` is not a valid ISO-8601 datetime string"
                with self.assertRaisesRegex(BadArgument, re.escape(exception_message)):
                    await converter.convert(self.context, datetime_string)

    async def test_hush_duration_converter_for_valid(self):
        """HushDurationConverter returns correct value for minutes duration or `"forever"` strings."""
        test_values = (
            ("0", 0),
            ("15", 15),
            ("10", 10),
            ("5m", 5),
            ("5M", 5),
            ("forever", -1),
        )
        converter = HushDurationConverter()
        for minutes_string, expected_minutes in test_values:
            with self.subTest(minutes_string=minutes_string, expected_minutes=expected_minutes):
                converted = await converter.convert(self.context, minutes_string)
                self.assertEqual(expected_minutes, converted)

    async def test_hush_duration_converter_for_invalid(self):
        """HushDurationConverter raises correct exception for invalid minutes duration strings."""
        test_values = (
            ("16", "Duration must be at most 15 minutes."),
            ("10d", "10d is not a valid minutes duration."),
            ("-1", "-1 is not a valid minutes duration."),
        )
        converter = HushDurationConverter()
        for invalid_minutes_string, exception_message in test_values:
            with (
                self.subTest(invalid_minutes_string=invalid_minutes_string, exception_message=exception_message),
                self.assertRaisesRegex(BadArgument, re.escape(exception_message)),
            ):
                await converter.convert(self.context, invalid_minutes_string)
