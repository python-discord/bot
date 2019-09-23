import asyncio
import logging
import textwrap
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from discord import (
    CategoryChannel,
    Colour,
    TextChannel,
    VoiceChannel,
)

from bot.cogs import information
from bot.constants import Emojis
from bot.decorators import InChannelCheckFailure
from tests.helpers import AsyncMock


@pytest.fixture()
def cog(simple_bot):
    return information.Information(simple_bot)


def role(name: str, id_: int):
    r = MagicMock()
    r.name = name
    r.id = id_
    r.mention = f'&{name}'
    return r


def member(status: str):
    m = MagicMock()
    m.status = status
    return m


@pytest.fixture()
def ctx(moderator_role, simple_ctx):
    simple_ctx.author.roles = [moderator_role]
    simple_ctx.guild.created_at = datetime(2001, 1, 1)
    simple_ctx.send = AsyncMock()
    return simple_ctx


def test_roles_info_command(cog, ctx):
    everyone_role = MagicMock()
    everyone_role.name = '@everyone'  # should be excluded in the output
    ctx.author.roles.append(everyone_role)
    ctx.guild.roles = ctx.author.roles

    cog.roles_info.can_run = AsyncMock()
    cog.roles_info.can_run.return_value = True

    coroutine = cog.roles_info.callback(cog, ctx)

    assert asyncio.run(coroutine) is None  # no rval
    ctx.send.assert_called_once()
    _, kwargs = ctx.send.call_args
    embed = kwargs.pop('embed')
    assert embed.title == "Role information"
    assert embed.colour == Colour.blurple()
    assert embed.description == f"`{ctx.guild.roles[0].id}` - {ctx.guild.roles[0].mention}\n"
    assert embed.footer.text == "Total roles: 1"


# There is no argument passed in here that we can use to test,
# so the return value would change constantly.
@patch('bot.cogs.information.time_since')
def test_server_info_command(time_since_patch, cog, ctx, moderator_role):
    time_since_patch.return_value = '2 days ago'

    ctx.guild.created_at = datetime(2001, 1, 1)
    ctx.guild.features = ('lemons', 'apples')
    ctx.guild.region = 'The Moon'
    ctx.guild.roles = [moderator_role]
    ctx.guild.channels = [
        TextChannel(
            state={},
            guild=ctx.guild,
            data={'id': 42, 'name': 'lemons-offering', 'position': 22, 'type': 'text'}
        ),
        CategoryChannel(
            state={},
            guild=ctx.guild,
            data={'id': 5125, 'name': 'the-lemon-collection', 'position': 22, 'type': 'category'}
        ),
        VoiceChannel(
            state={},
            guild=ctx.guild,
            data={'id': 15290, 'name': 'listen-to-lemon', 'position': 22, 'type': 'voice'}
        )
    ]
    ctx.guild.members = [
        member('online'), member('online'),
        member('idle'),
        member('dnd'), member('dnd'), member('dnd'), member('dnd'),
        member('offline'), member('offline'), member('offline')
    ]
    ctx.guild.member_count = 1_234
    ctx.guild.icon_url = 'a-lemon.png'

    coroutine = cog.server_info.callback(cog, ctx)
    assert asyncio.run(coroutine) is None  # no rval

    time_since_patch.assert_called_once_with(ctx.guild.created_at, precision='days')
    _, kwargs = ctx.send.call_args
    embed = kwargs.pop('embed')
    assert embed.colour == Colour.blurple()
    assert embed.description == textwrap.dedent(f"""
        **Server information**
        Created: {time_since_patch.return_value}
        Voice region: {ctx.guild.region}
        Features: {', '.join(ctx.guild.features)}

        **Counts**
        Members: {ctx.guild.member_count:,}
        Roles: {len(ctx.guild.roles)}
        Text: 1
        Voice: 1
        Channel categories: 1

        **Members**
        {Emojis.status_online} 2
        {Emojis.status_idle} 1
        {Emojis.status_dnd} 4
        {Emojis.status_offline} 3
        """)
    assert embed.thumbnail.url == 'a-lemon.png'


def test_user_info_on_other_users_from_non_moderator(ctx, cog):
    ctx.author = MagicMock()
    ctx.author.__eq__.return_value = False
    ctx.author.roles = []
    coroutine = cog.user_info.callback(cog, ctx, user='scragly')  # skip checks, pass args

    assert asyncio.run(coroutine) is None  # no rval
    ctx.send.assert_called_once_with(
        "You may not use this command on users other than yourself."
    )


def test_user_info_in_wrong_channel_from_non_moderator(ctx, cog):
    ctx.author = MagicMock()
    ctx.author.__eq__.return_value = False
    ctx.author.roles = []

    coroutine = cog.user_info.callback(cog, ctx)
    message = 'Sorry, but you may only use this command within <#267659945086812160>.'
    with pytest.raises(InChannelCheckFailure, match=message):
        assert asyncio.run(coroutine) is None  # no rval


def test_setup(simple_bot, caplog):
    information.setup(simple_bot)
    simple_bot.add_cog.assert_called_once()
    [record] = caplog.records

    assert record.message == "Cog loaded: Information"
    assert record.levelno == logging.INFO
