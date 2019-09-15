import asyncio
from unittest.mock import MagicMock

import pytest
from discord import Colour

from bot.cogs.token_remover import (
    DELETION_MESSAGE_TEMPLATE,
    TokenRemover,
    setup as setup_cog,
)
from bot.constants import Channels, Colours, Event, Icons
from tests.helpers import AsyncMock


@pytest.fixture()
def token_remover():
    bot = MagicMock()
    bot.get_cog.return_value = MagicMock()
    bot.get_cog.return_value.send_log_message = AsyncMock()
    return TokenRemover(bot=bot)


@pytest.fixture()
def message():
    message = MagicMock()
    message.author.__str__.return_value = 'lemon'
    message.author.bot = False
    message.author.avatar_url_as.return_value = 'picture-lemon.png'
    message.author.id = 42
    message.author.mention = '@lemon'
    message.channel.send = AsyncMock()
    message.channel.mention = '#lemonade-stand'
    message.content = ''
    message.delete = AsyncMock()
    message.id = 555
    return message


@pytest.mark.parametrize(
    ('content', 'expected'),
    (
        ('MTIz', True),  # 123
        ('YWJj', False),  # abc
    )
)
def test_is_valid_user_id(content: str, expected: bool):
    assert TokenRemover.is_valid_user_id(content) is expected


@pytest.mark.parametrize(
    ('content', 'expected'),
    (
        ('DN9r_A', True),  # stolen from dapi, thanks to the author of the 'token' tag!
        ('MTIz', False),  # 123
    )
)
def test_is_valid_timestamp(content: str, expected: bool):
    assert TokenRemover.is_valid_timestamp(content) is expected


def test_mod_log_property(token_remover):
    token_remover.bot.get_cog.return_value = 'lemon'
    assert token_remover.mod_log == 'lemon'
    token_remover.bot.get_cog.assert_called_once_with('ModLog')


def test_ignores_bot_messages(token_remover, message):
    message.author.bot = True
    coroutine = token_remover.on_message(message)
    assert asyncio.run(coroutine) is None


@pytest.mark.parametrize('content', ('', 'lemon wins'))
def test_ignores_messages_without_tokens(token_remover, message, content):
    message.content = content
    coroutine = token_remover.on_message(message)
    assert asyncio.run(coroutine) is None


@pytest.mark.parametrize('content', ('foo.bar.baz', 'x.y.'))
def test_ignores_invalid_tokens(token_remover, message, content):
    message.content = content
    coroutine = token_remover.on_message(message)
    assert asyncio.run(coroutine) is None


@pytest.mark.parametrize(
    'content, censored_token',
    (
        ('MTIz.DN9R_A.xyz', 'MTIz.DN9R_A.xxx'),
    )
)
def test_censors_valid_tokens(
    token_remover, message, content, censored_token, caplog
):
    message.content = content
    coroutine = token_remover.on_message(message)
    assert asyncio.run(coroutine) is None  # still no rval

    # asyncio logs some stuff about its reactor, discard it
    [_, record] = caplog.records
    assert record.message == (
        "Censored a seemingly valid token sent by lemon (`42`) in #lemonade-stand, "
        f"token was `{censored_token}`"
    )

    message.delete.assert_called_once_with()
    message.channel.send.assert_called_once_with(
        DELETION_MESSAGE_TEMPLATE.format(mention='@lemon')
    )
    token_remover.bot.get_cog.assert_called_with('ModLog')
    message.author.avatar_url_as.assert_called_once_with(static_format='png')

    mod_log = token_remover.bot.get_cog.return_value
    mod_log.ignore.assert_called_once_with(Event.message_delete, message.id)
    mod_log.send_log_message.assert_called_once_with(
        icon_url=Icons.token_removed,
        colour=Colour(Colours.soft_red),
        title="Token removed!",
        text=record.message,
        thumbnail='picture-lemon.png',
        channel_id=Channels.mod_alerts
    )


def test_setup(caplog):
    bot = MagicMock()
    setup_cog(bot)
    [record] = caplog.records

    bot.add_cog.assert_called_once()
    assert record.message == "Cog loaded: TokenRemover"
