import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from discord.ext.commands import BadArgument

from bot.converters import (
    ExpirationDate,
    TagContentConverter,
    TagNameConverter,
    ValidPythonIdentifier,
)


@pytest.mark.parametrize(
    ('value', 'expected'),
    (
        # sorry aliens
        ('2199-01-01T00:00:00', datetime(2199, 1, 1)),
    )
)
def test_expiration_date_converter_for_valid(value: str, expected: datetime):
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
