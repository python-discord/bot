import logging
from unittest.mock import MagicMock

import pytest
from discord.ext.commands import NoPrivateMessage

from bot.cogs import security


@pytest.fixture()
def cog():
    bot = MagicMock()
    return security.Security(bot)


@pytest.fixture()
def context():
    return MagicMock()


def test_check_additions(cog):
    cog.bot.check.assert_any_call(cog.check_on_guild)
    cog.bot.check.assert_any_call(cog.check_not_bot)


def test_check_not_bot_for_humans(cog, context):
    context.author.bot = False
    assert cog.check_not_bot(context)


def test_check_not_bot_for_robots(cog, context):
    context.author.bot = True
    assert not cog.check_not_bot(context)


def test_check_on_guild_outside_of_guild(cog, context):
    context.guild = None

    with pytest.raises(NoPrivateMessage, match="This command cannot be used in private messages."):
        cog.check_on_guild(context)


def test_check_on_guild_on_guild(cog, context):
    context.guild = "lemon's lemonade stand"
    assert cog.check_on_guild(context)


def test_security_cog_load(caplog):
    bot = MagicMock()
    security.setup(bot)
    bot.add_cog.assert_called_once()
    [record] = caplog.records
    assert record.message == "Cog loaded: Security"
    assert record.levelno == logging.INFO
