from unittest.mock import MagicMock

import pytest

from bot.utils import checks


@pytest.fixture()
def context():
    return MagicMock()


def test_with_role_check_without_guild(context):
    context.guild = None

    assert not checks.with_role_check(context)


def test_with_role_check_with_guild_without_required_role(context):
    context.guild = True
    context.author.roles = []

    assert not checks.with_role_check(context)


def test_with_role_check_with_guild_with_required_role(context):
    context.guild = True
    role = MagicMock()
    role.id = 42
    context.author.roles = (role,)

    assert checks.with_role_check(context, role.id)


def test_without_role_check_without_guild(context):
    context.guild = None

    assert not checks.without_role_check(context)


def test_without_role_check_with_unwanted_role(context):
    context.guild = True
    role = MagicMock()
    role.id = 42
    context.author.roles = (role,)

    assert not checks.without_role_check(context, role.id)


def test_without_role_check_without_unwanted_role(context):
    context.guild = True
    role = MagicMock()
    role.id = 42
    context.author.roles = (role,)

    assert checks.without_role_check(context, role.id + 10)


def test_in_channel_check_for_correct_channel(context):
    context.channel.id = [42]
    assert checks.in_channel_check(context, *context.channel.id)


def test_in_channel_check_for_incorrect_channel(context):
    context.channel.id = [42 + 10]
    assert not checks.in_channel_check(context, *context.channel.id)
