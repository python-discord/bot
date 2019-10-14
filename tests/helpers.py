from __future__ import annotations

import asyncio
import functools
import unittest.mock
from typing import Iterable, Optional

import discord
from discord.ext.commands import Bot, Context


def async_test(wrapped):
    """
    Run a test case via asyncio.
    Example:
        >>> @async_test
        ... async def lemon_wins():
        ...     assert True
    """

    @functools.wraps(wrapped)
    def wrapper(*args, **kwargs):
        return asyncio.run(wrapped(*args, **kwargs))
    return wrapper


# TODO: Remove me in Python 3.8
class AsyncMock(unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock async callables.

    Python 3.8 will introduce an AsyncMock class in the standard library that will have some more
    features; this stand-in only overwrites the `__call__` method to an async version.
    """

    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


class HashableMixin(discord.mixins.EqualityComparable):
    """
    Mixin that provides similar hashing and equality functionality as discord.py's `Hashable` mixin.

    Note: discord.py`s `Hashable` mixin bit-shifts `self.id` (`>> 22`); to prevent hash-collisions
    for the relative small `id` integers we generally use in tests, this bit-shift is omitted.
    """

    def __hash__(self):
        return self.id


class ColourMixin:
    """A mixin for Mocks that provides the aliasing of color->colour like discord.py does."""

    @property
    def color(self) -> discord.Colour:
        return self.colour

    @color.setter
    def color(self, color: discord.Colour) -> None:
        self.colour = color


class AttributeMock:
    """Ensures attributes of our mock types will be instantiated with the correct mock type."""

    def __new__(cls, *args, **kwargs):
        """Stops the regular parent class from propagating to newly mocked attributes."""
        if 'parent' in kwargs:
            return cls.attribute_mocktype(*args, **kwargs)

        return super().__new__(cls)


# Create a guild instance to get a realistic Mock of `discord.Guild`
guild_data = {
    'id': 1,
    'name': 'guild',
    'region': 'Europe',
    'verification_level': 2,
    'default_notications': 1,
    'afk_timeout': 100,
    'icon': "icon.png",
    'banner': 'banner.png',
    'mfa_level': 1,
    'splash': 'splash.png',
    'system_channel_id': 464033278631084042,
    'description': 'mocking is fun',
    'max_presences': 10_000,
    'max_members': 100_000,
    'preferred_locale': 'UTC',
    'owner_id': 1,
    'afk_channel_id': 464033278631084042,
}
guild_instance = discord.Guild(data=guild_data, state=unittest.mock.MagicMock())


class MockGuild(AttributeMock, unittest.mock.Mock, HashableMixin):
    """
    A `Mock` subclass to mock `discord.Guild` objects.

    A MockGuild instance will follow the specifications of a `discord.Guild` instance. This means
    that if the code you're testing tries to access an attribute or method that normally does not
    exist for a `discord.Guild` object this will raise an `AttributeError`. This is to make sure our
    tests fail if the code we're testing uses a `discord.Guild` object in the wrong way.

    One restriction of that is that if the code tries to access an attribute that normally does not
    exist for `discord.Guild` instance but was added dynamically, this will raise an exception with
    the mocked object. To get around that, you can set the non-standard attribute explicitly for the
    instance of `MockGuild`:

    >>> guild = MockGuild()
    >>> guild.attribute_that_normally_does_not_exist = unittest.mock.MagicMock()

    In addition to attribute simulation, mocked guild object will pass an `isinstance` check against
    `discord.Guild`:

    >>> guild = MockGuild()
    >>> isinstance(guild, discord.Guild)
    True

    For more info, see the `Mocking` section in `tests/README.md`.
    """

    attribute_mocktype = unittest.mock.MagicMock

    def __init__(
        self,
        guild_id: int = 1,
        roles: Optional[Iterable[MockRole]] = None,
        members: Optional[Iterable[MockMember]] = None,
        **kwargs,
    ) -> None:
        super().__init__(spec=guild_instance, **kwargs)

        self.id = guild_id

        self.roles = [MockRole("@everyone", 1)]
        if roles:
            self.roles.extend(roles)

        self.members = []
        if members:
            self.members.extend(members)

        # `discord.Guild` coroutines
        self.create_category_channel = AsyncMock()
        self.ban = AsyncMock()
        self.bans = AsyncMock()
        self.create_category = AsyncMock()
        self.create_custom_emoji = AsyncMock()
        self.create_role = AsyncMock()
        self.create_text_channel = AsyncMock()
        self.create_voice_channel = AsyncMock()
        self.delete = AsyncMock()
        self.edit = AsyncMock()
        self.estimate_pruned_members = AsyncMock()
        self.fetch_ban = AsyncMock()
        self.fetch_channels = AsyncMock()
        self.fetch_emoji = AsyncMock()
        self.fetch_emojis = AsyncMock()
        self.fetch_member = AsyncMock()
        self.invites = AsyncMock()
        self.kick = AsyncMock()
        self.leave = AsyncMock()
        self.prune_members = AsyncMock()
        self.unban = AsyncMock()
        self.vanity_invite = AsyncMock()
        self.webhooks = AsyncMock()
        self.widget = AsyncMock()


# Create a Role instance to get a realistic Mock of `discord.Role`
role_data = {'name': 'role', 'id': 1}
role_instance = discord.Role(guild=guild_instance, state=unittest.mock.MagicMock(), data=role_data)


class MockRole(AttributeMock, unittest.mock.Mock, ColourMixin, HashableMixin):
    """
    A Mock subclass to mock `discord.Role` objects.

    Instances of this class will follow the specifications of `discord.Role` instances. For more
    information, see the `MockGuild` docstring.
    """

    attribute_mocktype = unittest.mock.MagicMock

    def __init__(self, name: str = "role", role_id: int = 1, position: int = 1, **kwargs) -> None:
        super().__init__(spec=role_instance, **kwargs)

        self.name = name
        self.id = role_id
        self.position = position
        self.mention = f'&{self.name}'

        # 'discord.Role' coroutines
        self.delete = AsyncMock()
        self.edit = AsyncMock()

    def __lt__(self, other):
        """Simplified position-based comparisons similar to those of `discord.Role`."""
        return self.position < other.position


# Create a Member instance to get a realistic Mock of `discord.Member`
member_data = {'user': 'lemon', 'roles': [1]}
state_mock = unittest.mock.MagicMock()
member_instance = discord.Member(data=member_data, guild=guild_instance, state=state_mock)


class MockMember(AttributeMock, unittest.mock.Mock, ColourMixin, HashableMixin):
    """
    A Mock subclass to mock Member objects.

    Instances of this class will follow the specifications of `discord.Member` instances. For more
    information, see the `MockGuild` docstring.
    """

    attribute_mocktype = unittest.mock.MagicMock

    def __init__(
        self,
        name: str = "member",
        user_id: int = 1,
        roles: Optional[Iterable[MockRole]] = None,
        **kwargs,
    ) -> None:
        super().__init__(spec=member_instance, **kwargs)

        self.name = name
        self.id = user_id

        self.roles = [MockRole("@everyone", 1)]
        if roles:
            self.roles.extend(roles)

        self.mention = f"@{self.name}"

        # `discord.Member` coroutines
        self.add_roles = AsyncMock()
        self.ban = AsyncMock()
        self.edit = AsyncMock()
        self.fetch_message = AsyncMock()
        self.kick = AsyncMock()
        self.move_to = AsyncMock()
        self.pins = AsyncMock()
        self.remove_roles = AsyncMock()
        self.send = AsyncMock()
        self.trigger_typing = AsyncMock()
        self.unban = AsyncMock()


# Create a Bot instance to get a realistic MagicMock of `discord.ext.commands.Bot`
bot_instance = Bot(command_prefix=unittest.mock.MagicMock())


class MockBot(AttributeMock, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Bot objects.

    Instances of this class will follow the specifications of `discord.ext.commands.Bot` instances.
    For more information, see the `MockGuild` docstring.
    """

    attribute_mocktype = unittest.mock.MagicMock

    def __init__(self, **kwargs) -> None:
        super().__init__(spec=bot_instance, **kwargs)

        # `discord.ext.commands.Bot` coroutines
        self._before_invoke = AsyncMock()
        self._after_invoke = AsyncMock()
        self.application_info = AsyncMock()
        self.change_presence = AsyncMock()
        self.connect = AsyncMock()
        self.close = AsyncMock()
        self.create_guild = AsyncMock()
        self.delete_invite = AsyncMock()
        self.fetch_channel = AsyncMock()
        self.fetch_guild = AsyncMock()
        self.fetch_guilds = AsyncMock()
        self.fetch_invite = AsyncMock()
        self.fetch_user = AsyncMock()
        self.fetch_user_profile = AsyncMock()
        self.fetch_webhook = AsyncMock()
        self.fetch_widget = AsyncMock()
        self.get_context = AsyncMock()
        self.get_prefix = AsyncMock()
        self.invoke = AsyncMock()
        self.is_owner = AsyncMock()
        self.login = AsyncMock()
        self.logout = AsyncMock()
        self.on_command_error = AsyncMock()
        self.on_error = AsyncMock()
        self.process_commands = AsyncMock()
        self.request_offline_members = AsyncMock()
        self.start = AsyncMock()
        self.wait_until_ready = AsyncMock()
        self.wait_for = AsyncMock()


# Create a Context instance to get a realistic MagicMock of `discord.ext.commands.Context`
context_instance = Context(message=unittest.mock.MagicMock(), prefix=unittest.mock.MagicMock())


class MockContext(AttributeMock, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Context objects.

    Instances of this class will follow the specifications of `discord.ext.commands.Context`
    instances. For more information, see the `MockGuild` docstring.
    """

    attribute_mocktype = unittest.mock.MagicMock

    def __init__(self, **kwargs) -> None:
        super().__init__(spec=context_instance, **kwargs)
        self.bot = MockBot()
        self.guild = MockGuild()
        self.author = MockMember()
        self.command = unittest.mock.MagicMock()

        # `discord.ext.commands.Context` coroutines
        self.fetch_message = AsyncMock()
        self.invoke = AsyncMock()
        self.pins = AsyncMock()
        self.reinvoke = AsyncMock()
        self.send = AsyncMock()
        self.send_help = AsyncMock()
        self.trigger_typing = AsyncMock()


# Create a TextChannel instance to get a realistic MagicMock of `discord.TextChannel`
channel_data = {
    'id': 1,
    'type': 'TextChannel',
    'name': 'channel',
    'parent_id': 1234567890,
    'topic': 'topic',
    'position': 1,
    'nsfw': False,
    'last_message_id': 1,
}
state = unittest.mock.MagicMock()
guild = unittest.mock.MagicMock()
channel_instance = discord.TextChannel(state=state, guild=guild, data=channel_data)


class MockTextChannel(AttributeMock, unittest.mock.Mock, HashableMixin):
    """
    A MagicMock subclass to mock TextChannel objects.

    Instances of this class will follow the specifications of `discord.TextChannel` instances. For
    more information, see the `MockGuild` docstring.
    """

    attribute_mocktype = unittest.mock.MagicMock

    def __init__(self, name: str = 'channel', channel_id: int = 1, **kwargs) -> None:
        super().__init__(spec=channel_instance, **kwargs)
        self.id = channel_id
        self.name = name
        self.guild = MockGuild()
        self.mention = f"#{self.name}"

        # `discord.TextChannel` coroutines
        self.clone = AsyncMock()
        self.create_invite = AsyncMock()
        self.create_webhook = AsyncMock()
        self.delete = AsyncMock()
        self.delete_messages = AsyncMock()
        self.edit = AsyncMock()
        self.fetch_message = AsyncMock()
        self.invites = AsyncMock()
        self.pins = AsyncMock()
        self.purge = AsyncMock()
        self.send = AsyncMock()
        self.set_permissions = AsyncMock()
        self.trigger_typing = AsyncMock()
        self.webhooks = AsyncMock()


# Create a Message instance to get a realistic MagicMock of `discord.Message`
message_data = {
    'id': 1,
    'webhook_id': 431341013479718912,
    'attachments': [],
    'embeds': [],
    'application': 'Python Discord',
    'activity': 'mocking',
    'channel': unittest.mock.MagicMock(),
    'edited_timestamp': '2019-10-14T15:33:48+00:00',
    'type': 'message',
    'pinned': False,
    'mention_everyone': False,
    'tts': None,
    'content': 'content',
    'nonce': None,
}
state = unittest.mock.MagicMock()
channel = unittest.mock.MagicMock()
message_instance = discord.Message(state=state, channel=channel, data=message_data)


class MockMessage(AttributeMock, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Message objects.

    Instances of this class will follow the specifications of `discord.Message` instances. For more
    information, see the `MockGuild` docstring.
    """

    attribute_mocktype = unittest.mock.MagicMock

    def __init__(self, **kwargs) -> None:
        super().__init__(spec=message_instance, **kwargs)
        self.author = MockMember()

        # `discord.Message` coroutines
        self.ack = AsyncMock()
        self.add_reaction = AsyncMock()
        self.clear_reactions = AsyncMock()
        self.delete = AsyncMock()
        self.edit = AsyncMock()
        self.pin = AsyncMock()
        self.remove_reaction = AsyncMock()
        self.unpin = AsyncMock()
