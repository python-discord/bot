from __future__ import annotations

import asyncio
import functools
import inspect
import unittest.mock
from typing import Any, Iterable, Optional

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


class CustomMockMixin:
    """Ensures attributes of our mock types will be instantiated with the correct mock type."""

    child_mock_type = unittest.mock.MagicMock

    def __init__(self, spec: Any = None, **kwargs):
        super().__init__(spec=spec, **kwargs)
        if spec:
            self._extract_coroutine_methods_from_spec_instance(spec)

    def _get_child_mock(self, **kw):
        """
        Overwrite of the `_get_child_mock` method to stop the propagation of our custom mock classes.

        Mock objects automatically create children when you access an attribute or call a method on them. By default,
        the class of these children is the type of the parent itself. However, this would mean that the children created
        for our custom mock types would also be instances of that custom mock type. This is not desirable, as attributes
        of, e.g., a `Bot` object are not `Bot` objects themselves. The Python docs for `unittest.mock` hint that
        overwriting this method is the best way to deal with that.

        This override will look for an attribute called `child_mock_type` and use that as the type of the child mock.
        """
        klass = self.child_mock_type

        if self._mock_sealed:
            attribute = "." + kw["name"] if "name" in kw else "()"
            mock_name = self._extract_mock_name() + attribute
            raise AttributeError(mock_name)

        return klass(**kw)

    def _extract_coroutine_methods_from_spec_instance(self, source: Any) -> None:
        """Automatically detect coroutine functions in `source` and set them as AsyncMock attributes."""
        for name, _method in inspect.getmembers(source, inspect.iscoroutinefunction):
            setattr(self, name, AsyncMock())


# TODO: Remove me in Python 3.8
class AsyncMock(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock async callables.

    Python 3.8 will introduce an AsyncMock class in the standard library that will have some more
    features; this stand-in only overwrites the `__call__` method to an async version.
    """
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


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


class MockGuild(CustomMockMixin, unittest.mock.Mock, HashableMixin):
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


# Create a Role instance to get a realistic Mock of `discord.Role`
role_data = {'name': 'role', 'id': 1}
role_instance = discord.Role(guild=guild_instance, state=unittest.mock.MagicMock(), data=role_data)


class MockRole(CustomMockMixin, unittest.mock.Mock, ColourMixin, HashableMixin):
    """
    A Mock subclass to mock `discord.Role` objects.

    Instances of this class will follow the specifications of `discord.Role` instances. For more
    information, see the `MockGuild` docstring.
    """

    child_mock_type = unittest.mock.MagicMock

    def __init__(self, name: str = "role", role_id: int = 1, position: int = 1, **kwargs) -> None:
        super().__init__(spec=role_instance, **kwargs)

        self.name = name
        self.id = role_id
        self.position = position
        self.mention = f'&{self.name}'

    def __lt__(self, other):
        """Simplified position-based comparisons similar to those of `discord.Role`."""
        return self.position < other.position


# Create a Member instance to get a realistic Mock of `discord.Member`
member_data = {'user': 'lemon', 'roles': [1]}
state_mock = unittest.mock.MagicMock()
member_instance = discord.Member(data=member_data, guild=guild_instance, state=state_mock)


class MockMember(CustomMockMixin, unittest.mock.Mock, ColourMixin, HashableMixin):
    """
    A Mock subclass to mock Member objects.

    Instances of this class will follow the specifications of `discord.Member` instances. For more
    information, see the `MockGuild` docstring.
    """
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


# Create a Bot instance to get a realistic MagicMock of `discord.ext.commands.Bot`
bot_instance = Bot(command_prefix=unittest.mock.MagicMock())


class MockBot(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Bot objects.

    Instances of this class will follow the specifications of `discord.ext.commands.Bot` instances.
    For more information, see the `MockGuild` docstring.
    """
    def __init__(self, **kwargs) -> None:
        super().__init__(spec=bot_instance, **kwargs)

        # Our custom attributes and methods
        self.http_session = unittest.mock.MagicMock()
        self.api_client = unittest.mock.MagicMock()

        # self.wait_for is *not* a coroutine function, but returns a coroutine nonetheless and
        # and should therefore be awaited. (The documentation calls it a coroutine as well, which
        # is technically incorrect, since it's a regular def.)
        self.wait_for = AsyncMock()


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


class MockTextChannel(CustomMockMixin, unittest.mock.Mock, HashableMixin):
    """
    A MagicMock subclass to mock TextChannel objects.

    Instances of this class will follow the specifications of `discord.TextChannel` instances. For
    more information, see the `MockGuild` docstring.
    """
    def __init__(self, name: str = 'channel', channel_id: int = 1, **kwargs) -> None:
        super().__init__(spec=channel_instance, **kwargs)
        self.id = channel_id
        self.name = name
        self.guild = kwargs.get('guild', MockGuild())
        self.mention = f"#{self.name}"


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


# Create a Context instance to get a realistic MagicMock of `discord.ext.commands.Context`
context_instance = Context(message=unittest.mock.MagicMock(), prefix=unittest.mock.MagicMock())


class MockContext(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Context objects.

    Instances of this class will follow the specifications of `discord.ext.commands.Context`
    instances. For more information, see the `MockGuild` docstring.
    """
    def __init__(self, **kwargs) -> None:
        super().__init__(spec=context_instance, **kwargs)
        self.bot = kwargs.get('bot', MockBot())
        self.guild = kwargs.get('guild', MockGuild())
        self.author = kwargs.get('author', MockMember())
        self.channel = kwargs.get('channel', MockTextChannel())
        self.command = kwargs.get('command', unittest.mock.MagicMock())


class MockMessage(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Message objects.

    Instances of this class will follow the specifications of `discord.Message` instances. For more
    information, see the `MockGuild` docstring.
    """
    def __init__(self, **kwargs) -> None:
        super().__init__(spec=message_instance, **kwargs)
        self.author = kwargs.get('author', MockMember())
        self.channel = kwargs.get('channel', MockTextChannel())


emoji_data = {'require_colons': True, 'managed': True, 'id': 1, 'name': 'hyperlemon'}
emoji_instance = discord.Emoji(guild=MockGuild(), state=unittest.mock.MagicMock(), data=emoji_data)


class MockEmoji(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Emoji objects.

    Instances of this class will follow the specifications of `discord.Emoji` instances. For more
    information, see the `MockGuild` docstring.
    """
    def __init__(self, **kwargs) -> None:
        super().__init__(spec=emoji_instance, **kwargs)
        self.guild = kwargs.get('guild', MockGuild())

        # Get all coroutine functions and set them as AsyncMock attributes
        self._extract_coroutine_methods_from_spec_instance(emoji_instance)


partial_emoji_instance = discord.PartialEmoji(animated=False, name='guido')


class MockPartialEmoji(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock PartialEmoji objects.

    Instances of this class will follow the specifications of `discord.PartialEmoji` instances. For
    more information, see the `MockGuild` docstring.
    """
    def __init__(self, **kwargs) -> None:
        super().__init__(spec=partial_emoji_instance, **kwargs)


reaction_instance = discord.Reaction(message=MockMessage(), data={'me': True}, emoji=MockEmoji())


class MockReaction(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Reaction objects.

    Instances of this class will follow the specifications of `discord.Reaction` instances. For
    more information, see the `MockGuild` docstring.
    """
    def __init__(self, **kwargs) -> None:
        super().__init__(spec=reaction_instance, **kwargs)
        self.emoji = kwargs.get('emoji', MockEmoji())
        self.message = kwargs.get('message', MockMessage())
