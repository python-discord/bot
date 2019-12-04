import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from bot.utils import time
from tests.helpers import AsyncMock


class TimeTests(unittest.TestCase):
    """Test helper functions in bot.utils.time."""

    def setUp(self):
        pass

    def test_humanize_delta_handle_unknown_units(self):
        """humanize_delta should be able to handle unknown units, and will not abort."""
        test_cases = (
            # Does not abort for unknown units, as the unit name is checked
            # against the attribute of the relativedelta instance.
            (relativedelta(days=2, hours=2), 'elephants', 2, '2 days and 2 hours'),
        )

        for delta, precision, max_units, expected in test_cases:
            self.assertEqual(time.humanize_delta(delta, precision, max_units), expected)

    def test_humanize_delta_handle_high_units(self):
        """humanize_delta should be able to handle very high units."""
        test_cases = (
            # Very high maximum units, but it only ever iterates over
            # each value the relativedelta might have.
            (relativedelta(days=2, hours=2), 'hours', 20, '2 days and 2 hours'),
        )

        for delta, precision, max_units, expected in test_cases:
            self.assertEqual(time.humanize_delta(delta, precision, max_units), expected)

    def test_humanize_delta_should_normal_usage(self):
        """Testing humanize delta."""
        test_cases = (
            (relativedelta(days=2), 'seconds', 1, '2 days'),
            (relativedelta(days=2, hours=2), 'seconds', 2, '2 days and 2 hours'),
            (relativedelta(days=2, hours=2), 'seconds', 1, '2 days'),
            (relativedelta(days=2, hours=2), 'days', 2, '2 days'),
        )

        for delta, precision, max_units, expected in test_cases:
            self.assertEqual(time.humanize_delta(delta, precision, max_units), expected)

    def test_humanize_delta_raises_for_invalid_max_units(self):
        """humanize_delta should raises ValueError('max_units must be positive') for invalid max_units."""
        test_cases = (-1, 0)

        for max_units in test_cases:
            with self.assertRaises(ValueError) as error:
                time.humanize_delta(relativedelta(days=2, hours=2), 'hours', max_units)
                self.assertEqual(str(error), 'max_units must be positive')

    def test_parse_rfc1123(self):
        """Testing parse_rfc1123."""
        self.assertEqual(
            time.parse_rfc1123('Sun, 15 Sep 2019 12:00:00 GMT'),
            datetime(2019, 9, 15, 12, 0, 0, tzinfo=timezone.utc)
        )

    def test_format_infraction(self):
        """Testing format_infraction."""
        self.assertEqual(time.format_infraction('2019-12-12T00:01:00Z'), '2019-12-12 00:01')

    @patch('asyncio.sleep', new_callable=AsyncMock)
    def test_wait_until(self, mock):
        """Testing wait_until."""
        start = datetime(2019, 1, 1, 0, 0)
        then = datetime(2019, 1, 1, 0, 10)

        # No return value
        self.assertIs(asyncio.run(time.wait_until(then, start)), None)

        mock.assert_called_once_with(10 * 60)

    def test_format_infraction_with_duration_none_expiry(self):
        """format_infraction_with_duration should work for None expiry."""
        self.assertEqual(time.format_infraction_with_duration(None), None)

        # To make sure that date_from and max_units are not touched
        self.assertEqual(time.format_infraction_with_duration(None, date_from='Why hello there!'), None)
        self.assertEqual(time.format_infraction_with_duration(None, max_units=float('inf')), None)
        self.assertEqual(
            time.format_infraction_with_duration(None, date_from='Why hello there!', max_units=float('inf')),
            None
        )

    def test_format_infraction_with_duration_custom_units(self):
        """format_infraction_with_duration should work for custom max_units."""
        self.assertEqual(
            time.format_infraction_with_duration('2019-12-12T00:01:00Z', datetime(2019, 12, 11, 12, 5, 5), 6),
            '2019-12-12 00:01 (11 hours, 55 minutes and 55 seconds)'
        )

        self.assertEqual(
            time.format_infraction_with_duration('2019-11-23T20:09:00Z', datetime(2019, 4, 25, 20, 15), 20),
            '2019-11-23 20:09 (6 months, 28 days, 23 hours and 54 minutes)'
        )

    def test_format_infraction_with_duration_normal_usage(self):
        """format_infraction_with_duration should work for normal usage, across various durations."""
        test_cases = (
            ('2019-12-12T00:01:00Z', datetime(2019, 12, 11, 12, 0, 5), 2, '2019-12-12 00:01 (12 hours and 55 seconds)'),
            ('2019-12-12T00:01:00Z', datetime(2019, 12, 11, 12, 0, 5), 1, '2019-12-12 00:01 (12 hours)'),
            ('2019-12-12T00:00:00Z', datetime(2019, 12, 11, 23, 59), 2, '2019-12-12 00:00 (1 minute)'),
            ('2019-11-23T20:09:00Z', datetime(2019, 11, 15, 20, 15), 2, '2019-11-23 20:09 (7 days and 23 hours)'),
            ('2019-11-23T20:09:00Z', datetime(2019, 4, 25, 20, 15), 2, '2019-11-23 20:09 (6 months and 28 days)'),
            ('2019-11-23T20:58:00Z', datetime(2019, 11, 23, 20, 53), 2, '2019-11-23 20:58 (5 minutes)'),
            ('2019-11-24T00:00:00Z', datetime(2019, 11, 23, 23, 59, 0), 2, '2019-11-24 00:00 (1 minute)'),
            ('2019-11-23T23:59:00Z', datetime(2017, 7, 21, 23, 0), 2, '2019-11-23 23:59 (2 years and 4 months)'),
            ('2019-11-23T23:59:00Z', datetime(2019, 11, 23, 23, 49, 5), 2,
             '2019-11-23 23:59 (9 minutes and 55 seconds)'),
            (None, datetime(2019, 11, 23, 23, 49, 5), 2, None),
        )

        for expiry, date_from, max_units, expected in test_cases:
            self.assertEqual(time.format_infraction_with_duration(expiry, date_from, max_units), expected)
