import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from dateutil.relativedelta import relativedelta

from bot.utils import time
from tests.helpers import AsyncMock


@pytest.mark.parametrize(
    ('delta', 'precision', 'max_units', 'expected'),
    (
        (relativedelta(days=2), 'seconds', 1, '2 days'),
        (relativedelta(days=2, hours=2), 'seconds', 2, '2 days and 2 hours'),
        (relativedelta(days=2, hours=2), 'seconds', 1, '2 days'),
        (relativedelta(days=2, hours=2), 'days', 2, '2 days'),

        # Does not abort for unknown units, as the unit name is checked
        # against the attribute of the relativedelta instance.
        (relativedelta(days=2, hours=2), 'elephants', 2, '2 days and 2 hours'),

        # Very high maximum units, but it only ever iterates over
        # each value the relativedelta might have.
        (relativedelta(days=2, hours=2), 'hours', 20, '2 days and 2 hours'),
    )
)
def test_humanize_delta(
        delta: relativedelta,
        precision: str,
        max_units: int,
        expected: str
):
    assert time.humanize_delta(delta, precision, max_units) == expected


@pytest.mark.parametrize('max_units', (-1, 0))
def test_humanize_delta_raises_for_invalid_max_units(max_units: int):
    with pytest.raises(ValueError, match='max_units must be positive'):
        time.humanize_delta(relativedelta(days=2, hours=2), 'hours', max_units)


@pytest.mark.parametrize(
    ('stamp', 'expected'),
    (
        ('Sun, 15 Sep 2019 12:00:00 GMT', datetime(2019, 9, 15, 12, 0, 0, tzinfo=timezone.utc)),
    )
)
def test_parse_rfc1123(stamp: str, expected: str):
    assert time.parse_rfc1123(stamp) == expected


@patch('asyncio.sleep', new_callable=AsyncMock)
def test_wait_until(sleep_patch):
    start = datetime(2019, 1, 1, 0, 0)
    then = datetime(2019, 1, 1, 0, 10)

    # No return value
    assert asyncio.run(time.wait_until(then, start)) is None

    sleep_patch.assert_called_once_with(10 * 60)


@pytest.mark.parametrize(
    ('date_from', 'date_to', 'expected'),
    (
        (datetime(2019, 12, 12, 0, 1), datetime(2019, 12, 12, 12, 0, 5), '11 hours, 59 minutes'),
        (datetime(2019, 12, 12), datetime(2019, 12, 11, 23, 59), '1 minute'),
        (datetime(2019, 11, 23, 20, 9), datetime(2019, 11, 30, 20, 15), '1 week, 6 minutes'),
        (datetime(2019, 11, 23, 20, 9), datetime(2019, 4, 25, 20, 15), '7 months, 2 weeks'),
        (datetime(2019, 11, 23, 20, 58), datetime(2019, 11, 23, 21, 3), '5 minutes'),
        (datetime(2019, 11, 23, 23, 59), datetime(2019, 11, 24, 0, 0), '1 minute'),
        (datetime(2019, 11, 23, 23, 59), datetime(2022, 11, 23, 23, 0), '3 years, 3 months'),
        (datetime(2019, 11, 23, 23, 59), datetime(2019, 11, 23, 23, 49, 5), '9 minutes, 55 seconds'),
    )
)
def test_get_duration(date_from: datetime, date_to: datetime, expected: str):
    assert time.get_duration(date_from, date_to) == expected
