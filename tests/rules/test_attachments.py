import asyncio
from dataclasses import dataclass
from typing import Any, List

import pytest

from bot.rules import attachments


# Using `MagicMock` sadly doesn't work for this usecase
# since it's __eq__ compares the MagicMock's ID. We just
# want to compare the actual attributes we set.
@dataclass
class FakeMessage:
    author: str
    attachments: List[Any]


def msg(total_attachments: int):
    return FakeMessage(author='lemon', attachments=list(range(total_attachments)))


@pytest.mark.parametrize(
    'messages',
    (
        (msg(0), msg(0), msg(0)),
        (msg(2), msg(2)),
        (msg(0),),
    )
)
def test_allows_messages_without_too_many_attachments(messages):
    last_message, *recent_messages = messages
    coro = attachments.apply(last_message, recent_messages, {'max': 5})
    assert asyncio.run(coro) is None


@pytest.mark.parametrize(
    ('messages', 'relevant_messages', 'total'),
    (
        ((msg(4), msg(0), msg(6)), [msg(4), msg(6)], 10),
        ((msg(6),), [msg(6)], 6),
        ((msg(1),) * 6, [msg(1)] * 6, 6),
    )
)
def test_disallows_messages_with_too_many_attachments(messages, relevant_messages, total):
    last_message, *recent_messages = messages
    coro = attachments.apply(last_message, recent_messages, {'max': 5})
    assert asyncio.run(coro) == (
        f"sent {total} attachments in 5s",
        ('lemon',),
        relevant_messages
    )
