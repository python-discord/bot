import asyncio
import datetime
from unittest.mock import MagicMock, patch

import pytest
from dateutil.relativedelta import relativedelta
from discord.ext.commands import BadArgument

from bot.converters import (
    Duration,
    TagContentConverter,
    TagNameConverter,
    ValidPythonIdentifier,
)


@pytest.mark.parametrize(
    ('value', 'expected'),
    (
        ('hello', 'hello'),
        ('  h ello  ', 'h ello')
    )
)
def test_tag_content_converter_for_valid(value: str, expected: str):
    assert asyncio.run(TagContentConverter.convert(None, value)) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    (
        ('', "Tag contents should not be empty, or filled with whitespace."),
        ('   ', "Tag contents should not be empty, or filled with whitespace.")
    )
)
def test_tag_content_converter_for_invalid(value: str, expected: str):
    context = MagicMock()
    context.author = 'bob'

    with pytest.raises(BadArgument, match=expected):
        asyncio.run(TagContentConverter.convert(context, value))


@pytest.mark.parametrize(
    ('value', 'expected'),
    (
        ('tracebacks', 'tracebacks'),
        ('Tracebacks', 'tracebacks'),
        ('  Tracebacks  ', 'tracebacks'),
    )
)
def test_tag_name_converter_for_valid(value: str, expected: str):
    assert asyncio.run(TagNameConverter.convert(None, value)) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    (
        ('👋', "Don't be ridiculous, you can't use that character!"),
        ('', "Tag names should not be empty, or filled with whitespace."),
        ('  ', "Tag names should not be empty, or filled with whitespace."),
        ('42', "Tag names can't be numbers."),
        # Escape question mark as this is evaluated as regular expression.
        ('x' * 128, r"Are you insane\? That's way too long!"),
    )
)
def test_tag_name_converter_for_invalid(value: str, expected: str):
    context = MagicMock()
    context.author = 'bob'

    with pytest.raises(BadArgument, match=expected):
        asyncio.run(TagNameConverter.convert(context, value))


@pytest.mark.parametrize('value', ('foo', 'lemon'))
def test_valid_python_identifier_for_valid(value: str):
    assert asyncio.run(ValidPythonIdentifier.convert(None, value)) == value


@pytest.mark.parametrize('value', ('nested.stuff', '#####'))
def test_valid_python_identifier_for_invalid(value: str):
    with pytest.raises(BadArgument, match=f'`{value}` is not a valid Python identifier'):
        asyncio.run(ValidPythonIdentifier.convert(None, value))


FIXED_UTC_NOW = datetime.datetime.fromisoformat('2019-01-01T00:00:00')


@pytest.fixture(
    params=(
        # Simple duration strings
        ('1Y', {"years": 1}),
        ('1y', {"years": 1}),
        ('1year', {"years": 1}),
        ('1years', {"years": 1}),
        ('1m', {"months": 1}),
        ('1month', {"months": 1}),
        ('1months', {"months": 1}),
        ('1w', {"weeks": 1}),
        ('1W', {"weeks": 1}),
        ('1week', {"weeks": 1}),
        ('1weeks', {"weeks": 1}),
        ('1d', {"days": 1}),
        ('1D', {"days": 1}),
        ('1day', {"days": 1}),
        ('1days', {"days": 1}),
        ('1h', {"hours": 1}),
        ('1H', {"hours": 1}),
        ('1hour', {"hours": 1}),
        ('1hours', {"hours": 1}),
        ('1M', {"minutes": 1}),
        ('1minute', {"minutes": 1}),
        ('1minutes', {"minutes": 1}),
        ('1s', {"seconds": 1}),
        ('1S', {"seconds": 1}),
        ('1second', {"seconds": 1}),
        ('1seconds', {"seconds": 1}),

        # Complex duration strings
        (
            '1y1m1w1d1H1M1S',
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
        ('5y100S', {"years": 5, "seconds": 100}),
        ('2w28H', {"weeks": 2, "hours": 28}),

        # Duration strings with spaces
        ('1 year 2 months', {"years": 1, "months": 2}),
        ('1d 2H', {"days": 1, "hours": 2}),
        ('1 week2 days', {"weeks": 1, "days": 2}),
    )
)
def create_future_datetime(request):
    """Yields duration string and target datetime.datetime object."""
    duration, duration_dict = request.param
    future_datetime = FIXED_UTC_NOW + relativedelta(**duration_dict)
    yield duration, future_datetime


def test_duration_converter_for_valid(create_future_datetime: tuple):
    converter = Duration()
    duration, expected = create_future_datetime
    with patch('bot.converters.datetime') as mock_datetime:
        mock_datetime.utcnow.return_value = FIXED_UTC_NOW
        assert asyncio.run(converter.convert(None, duration)) == expected


@pytest.mark.parametrize(
    ('duration'),
    (
        # Units in wrong order
        ('1d1w'),
        ('1s1y'),

        # Duplicated units
        ('1 year 2 years'),
        ('1 M 10 minutes'),

        # Unknown substrings
        ('1MVes'),
        ('1y3breads'),

        # Missing amount
        ('ym'),

        # Incorrect whitespace
        (" 1y"),
        ("1S "),
        ("1y  1m"),

        # Garbage
        ('Guido van Rossum'),
        ('lemon lemon lemon lemon lemon lemon lemon'),
    )
)
def test_duration_converter_for_invalid(duration: str):
    converter = Duration()
    with pytest.raises(BadArgument, match=f'`{duration}` is not a valid duration string.'):
        asyncio.run(converter.convert(None, duration))
