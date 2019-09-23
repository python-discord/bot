import asyncio
import datetime
from unittest.mock import MagicMock, patch

import pytest
from discord.ext.commands import BadArgument

from bot.converters import (
    Duration,
    ExpirationDate,
    TagContentConverter,
    TagNameConverter,
    ValidPythonIdentifier,
)


@pytest.mark.parametrize(
    ('value', 'expected'),
    (
        # sorry aliens
        ('2199-01-01T00:00:00', datetime.datetime(2199, 1, 1)),
    )
)
def test_expiration_date_converter_for_valid(value: str, expected: datetime.datetime):
    converter = ExpirationDate()
    assert asyncio.run(converter.convert(None, value)) == expected


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


@pytest.mark.parametrize(
    ('duration', 'expected'),
    (
        # Simple duration strings
        ('1Y', datetime.datetime.fromisoformat('2020-01-01T00:00:00')),
        ('1y', datetime.datetime.fromisoformat('2020-01-01T00:00:00')),
        ('1year', datetime.datetime.fromisoformat('2020-01-01T00:00:00')),
        ('1years', datetime.datetime.fromisoformat('2020-01-01T00:00:00')),
        ('1m', datetime.datetime.fromisoformat('2019-02-01T00:00:00')),
        ('1month', datetime.datetime.fromisoformat('2019-02-01T00:00:00')),
        ('1months', datetime.datetime.fromisoformat('2019-02-01T00:00:00')),
        ('1w', datetime.datetime.fromisoformat('2019-01-08T00:00:00')),
        ('1W', datetime.datetime.fromisoformat('2019-01-08T00:00:00')),
        ('1week', datetime.datetime.fromisoformat('2019-01-08T00:00:00')),
        ('1weeks', datetime.datetime.fromisoformat('2019-01-08T00:00:00')),
        ('1d', datetime.datetime.fromisoformat('2019-01-02T00:00:00')),
        ('1D', datetime.datetime.fromisoformat('2019-01-02T00:00:00')),
        ('1day', datetime.datetime.fromisoformat('2019-01-02T00:00:00')),
        ('1days', datetime.datetime.fromisoformat('2019-01-02T00:00:00')),
        ('1h', datetime.datetime.fromisoformat('2019-01-01T01:00:00')),
        ('1H', datetime.datetime.fromisoformat('2019-01-01T01:00:00')),
        ('1hour', datetime.datetime.fromisoformat('2019-01-01T01:00:00')),
        ('1hours', datetime.datetime.fromisoformat('2019-01-01T01:00:00')),
        ('1M', datetime.datetime.fromisoformat('2019-01-01T00:01:00')),
        ('1minute', datetime.datetime.fromisoformat('2019-01-01T00:01:00')),
        ('1minutes', datetime.datetime.fromisoformat('2019-01-01T00:01:00')),
        ('1s', datetime.datetime.fromisoformat('2019-01-01T00:00:01')),
        ('1S', datetime.datetime.fromisoformat('2019-01-01T00:00:01')),
        ('1second', datetime.datetime.fromisoformat('2019-01-01T00:00:01')),
        ('1seconds', datetime.datetime.fromisoformat('2019-01-01T00:00:01')),

        # Complex duration strings
        ('1y1m1w1d1H1M1S', datetime.datetime.fromisoformat('2020-02-09T01:01:01')),
        ('5y100S', datetime.datetime.fromisoformat('2024-01-01T00:01:40')),
        ('2w28H', datetime.datetime.fromisoformat('2019-01-16T04:00:00')),
    )
)
def test_duration_converter_for_valid(duration: str, expected: datetime):
    converter = Duration()

    with patch('bot.converters.datetime') as mock_datetime:
        mock_datetime.utcnow.return_value = FIXED_UTC_NOW
        assert asyncio.run(converter.convert(None, duration)) == expected


@pytest.mark.parametrize(
    ('duration'),
    (
        # Units in wrong order
        ('1d1w'),
        ('1s1y'),

        # Unknown substrings
        ('1MVes'),
        ('1y3breads'),

        # Missing amount
        ('ym'),

        # Garbage
        ('Guido van Rossum'),
        ('lemon lemon lemon lemon lemon lemon lemon'),
    )
)
def test_duration_converter_for_invalid(duration: str):
    converter = Duration()
    with pytest.raises(BadArgument, match=f'`{duration}` is not a valid duration string.'):
        asyncio.run(converter.convert(None, duration))
