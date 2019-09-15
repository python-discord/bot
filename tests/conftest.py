from unittest.mock import MagicMock

import pytest

from bot.constants import Roles
from tests.helpers import AsyncMock


@pytest.fixture()
def moderator_role():
    mock = MagicMock()
    mock.id = Roles.moderator
    mock.name = 'Moderator'
    mock.mention = f'&{mock.name}'
    return mock


@pytest.fixture()
def simple_bot():
    mock = MagicMock()
    mock._before_invoke = AsyncMock()
    mock._after_invoke = AsyncMock()
    mock.can_run = AsyncMock()
    mock.can_run.return_value = True
    return mock


@pytest.fixture()
def simple_ctx(simple_bot):
    mock = MagicMock()
    mock.bot = simple_bot
    return mock
