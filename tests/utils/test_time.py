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
    )
)
def test_humanize_delta(
        delta: relativedelta,
        precision: str,
        max_units: int,
        expected: str
):
    assert time.humanize_delta(delta, precision, max_units) == expected


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
