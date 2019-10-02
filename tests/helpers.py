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
    """A mixin of Mocks that provides the aliasing of color->colour like discord.py does."""

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

    def __init__(
        self,
        name: str = "role",
        role_id: int = 1,
        position: int = 1,
        **kwargs,
    ) -> None:
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
        self.send = AsyncMock()


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
        self._before_invoke = AsyncMock()
        self._after_invoke = AsyncMock()
        self.user = MockMember(name="Python", user_id=123456789)


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
        self.send = AsyncMock()
        self.guild = MockGuild()
        self.author = MockMember()
        self.command = unittest.mock.MagicMock()
