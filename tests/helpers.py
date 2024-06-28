from __future__ import annotations

import collections
import itertools
import logging
import unittest.mock
from asyncio import AbstractEventLoop
from collections.abc import Iterable
from contextlib import contextmanager
from functools import cached_property

import discord
from aiohttp import ClientSession
from discord.ext.commands import Context
from pydis_core.async_stats import AsyncStatsClient
from pydis_core.site_api import APIClient

from bot.bot import Bot
from tests._autospec import autospec  # noqa: F401 other modules import it via this module

for logger in logging.Logger.manager.loggerDict.values():
    # Set all loggers to CRITICAL by default to prevent screen clutter during testing

    if not isinstance(logger, logging.Logger):
        # There might be some logging.PlaceHolder objects in there
        continue

    logger.setLevel(logging.CRITICAL)


class HashableMixin(discord.mixins.EqualityComparable):
    """
    Mixin that provides similar hashing and equality functionality as discord.py's `Hashable` mixin.

    Note: discord.py`s `Hashable` mixin bit-shifts `self.id` (`>> 22`); to prevent hash-collisions
    for the relative small `id` integers we generally use in tests, this bit-shift is omitted.
    """

    def __hash__(self):
        return self.id


class ColourMixin:
    """A mixin for Mocks that provides the aliasing of (accent_)color->(accent_)colour like discord.py does."""

    @property
    def color(self) -> discord.Colour:
        return self.colour

    @color.setter
    def color(self, color: discord.Colour) -> None:
        self.colour = color

    @property
    def accent_color(self) -> discord.Colour:
        return self.accent_colour

    @accent_color.setter
    def accent_color(self, color: discord.Colour) -> None:
        self.accent_colour = color


class CustomMockMixin:
    """
    Provides common functionality for our custom Mock types.

    The `_get_child_mock` method automatically returns an AsyncMock for coroutine methods of the mock
    object. As discord.py also uses synchronous methods that nonetheless return coroutine objects, the
    class attribute `additional_spec_asyncs` can be overwritten with an iterable containing additional
    attribute names that should also mocked with an AsyncMock instead of a regular MagicMock/Mock. The
    class method `spec_set` can be overwritten with the object that should be uses as the specification
    for the mock.

    Mock/MagicMock subclasses that use this mixin only need to define `__init__` method if they need to
    implement custom behavior.
    """

    child_mock_type = unittest.mock.MagicMock
    discord_id = itertools.count(0)
    spec_set = None
    additional_spec_asyncs = None

    def __init__(self, **kwargs):
        name = kwargs.pop("name", None)  # `name` has special meaning for Mock classes, so we need to set it manually.
        super().__init__(spec_set=self.spec_set, **kwargs)

        if self.additional_spec_asyncs:
            self._spec_asyncs.extend(self.additional_spec_asyncs)

        if name:
            self.name = name

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
        _new_name = kw.get("_new_name")
        if _new_name in self.__dict__["_spec_asyncs"]:
            return unittest.mock.AsyncMock(**kw)

        _type = type(self)
        if issubclass(_type, unittest.mock.MagicMock) and _new_name in unittest.mock._async_method_magics:
            # Any asynchronous magic becomes an AsyncMock
            klass = unittest.mock.AsyncMock
        else:
            klass = self.child_mock_type

        if self._mock_sealed:
            attribute = "." + kw["name"] if "name" in kw else "()"
            mock_name = self._extract_mock_name() + attribute
            raise AttributeError(mock_name)

        return klass(**kw)


# Create a guild instance to get a realistic Mock of `discord.Guild`
guild_data = {
    "id": 1,
    "name": "guild",
    "region": "Europe",
    "verification_level": 2,
    "default_notications": 1,
    "afk_timeout": 100,
    "icon": "icon.png",
    "banner": "banner.png",
    "mfa_level": 1,
    "splash": "splash.png",
    "system_channel_id": 464033278631084042,
    "description": "mocking is fun",
    "max_presences": 10_000,
    "max_members": 100_000,
    "preferred_locale": "UTC",
    "owner_id": 1,
    "afk_channel_id": 464033278631084042,
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
    spec_set = guild_instance

    def __init__(self, roles: Iterable[MockRole] | None = None, **kwargs) -> None:
        default_kwargs = {"id": next(self.discord_id), "members": [], "chunked": True}
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))

        if roles:
            self.roles = [
                MockRole(name="@everyone", position=1, id=0),
                *roles
            ]

    @cached_property
    def roles(self) -> list[MockRole]:
        """Cached roles property."""
        return [MockRole(name="@everyone", position=1, id=0)]


# Create a Role instance to get a realistic Mock of `discord.Role`
role_data = {"name": "role", "id": 1}
role_instance = discord.Role(guild=guild_instance, state=unittest.mock.MagicMock(), data=role_data)


class MockRole(CustomMockMixin, unittest.mock.Mock, ColourMixin, HashableMixin):
    """
    A Mock subclass to mock `discord.Role` objects.

    Instances of this class will follow the specifications of `discord.Role` instances. For more
    information, see the `MockGuild` docstring.
    """
    spec_set = role_instance

    def __init__(self, **kwargs) -> None:
        default_kwargs = {
            "id": next(self.discord_id),
            "name": "role",
            "position": 1,
            "colour": discord.Colour(0xdeadbf),
            "permissions": discord.Permissions(),
        }
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))

        if isinstance(self.colour, int):
            self.colour = discord.Colour(self.colour)

        if isinstance(self.permissions, int):
            self.permissions = discord.Permissions(self.permissions)

        if "mention" not in kwargs:
            self.mention = f"&{self.name}"

    def __lt__(self, other):
        """Simplified position-based comparisons similar to those of `discord.Role`."""
        return self.position < other.position

    def __ge__(self, other):
        """Simplified position-based comparisons similar to those of `discord.Role`."""
        return self.position >= other.position


# Create a Member instance to get a realistic Mock of `discord.Member`
member_data = {"user": "lemon", "roles": [1], "flags": 2}
state_mock = unittest.mock.MagicMock()
member_instance = discord.Member(data=member_data, guild=guild_instance, state=state_mock)


class MockMember(CustomMockMixin, unittest.mock.Mock, ColourMixin, HashableMixin):
    """
    A Mock subclass to mock Member objects.

    Instances of this class will follow the specifications of `discord.Member` instances. For more
    information, see the `MockGuild` docstring.
    """
    spec_set = member_instance

    def __init__(self, roles: Iterable[MockRole] | None = None, **kwargs) -> None:
        default_kwargs = {"name": "member", "id": next(self.discord_id), "bot": False, "pending": False}
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))

        self.roles = [MockRole(name="@everyone", position=1, id=0)]
        if roles:
            self.roles.extend(roles)
        self.top_role = max(self.roles)

        if "mention" not in kwargs:
            self.mention = f"@{self.name}"

    def get_role(self, role_id: int) -> MockRole | None:
        return discord.utils.get(self.roles, id=role_id)


# Create a User instance to get a realistic Mock of `discord.User`
_user_data_mock = collections.defaultdict(unittest.mock.MagicMock, {
    "accent_color": 0
})
user_instance = discord.User(
    data=unittest.mock.MagicMock(get=unittest.mock.Mock(side_effect=_user_data_mock.get)),
    state=unittest.mock.MagicMock()
)


class MockUser(CustomMockMixin, unittest.mock.Mock, ColourMixin, HashableMixin):
    """
    A Mock subclass to mock User objects.

    Instances of this class will follow the specifications of `discord.User` instances. For more
    information, see the `MockGuild` docstring.
    """
    spec_set = user_instance

    def __init__(self, **kwargs) -> None:
        default_kwargs = {"name": "user", "id": next(self.discord_id), "bot": False}
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))

        if "mention" not in kwargs:
            self.mention = f"@{self.name}"


class MockAPIClient(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock APIClient objects.

    Instances of this class will follow the specifications of `bot.api.APIClient` instances.
    For more information, see the `MockGuild` docstring.
    """
    spec_set = APIClient


def _get_mock_loop() -> unittest.mock.Mock:
    """Return a mocked asyncio.AbstractEventLoop."""
    loop = unittest.mock.create_autospec(spec=AbstractEventLoop, spec_set=True)

    # Since calling `create_task` on our MockBot does not actually schedule the coroutine object
    # as a task in the asyncio loop, this `side_effect` calls `close()` on the coroutine object
    # to prevent "has not been awaited"-warnings.
    def mock_create_task(coroutine, **kwargs):
        coroutine.close()
        return unittest.mock.Mock()
    loop.create_task.side_effect = mock_create_task

    return loop


class MockBot(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Bot objects.

    Instances of this class will follow the specifications of `discord.ext.commands.Bot` instances.
    For more information, see the `MockGuild` docstring.
    """
    spec_set = Bot(
        command_prefix=unittest.mock.MagicMock(),
        loop=_get_mock_loop(),
        redis_session=unittest.mock.MagicMock(),
        http_session=unittest.mock.MagicMock(),
        allowed_roles=[1],
        guild_id=1,
        intents=discord.Intents.all(),
    )
    additional_spec_asyncs = ("wait_for",)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_cog = unittest.mock.AsyncMock()

    @cached_property
    def loop(self) -> unittest.mock.Mock:
        """Cached loop property."""
        return _get_mock_loop()

    @cached_property
    def api_client(self) -> MockAPIClient:
        """Cached api_client property."""
        return MockAPIClient()

    @cached_property
    def http_session(self) -> unittest.mock.Mock:
        """Cached http_session property."""
        return unittest.mock.create_autospec(spec=ClientSession, spec_set=True)

    @cached_property
    def stats(self) -> unittest.mock.Mock:
        """Cached stats property."""
        return unittest.mock.create_autospec(spec=AsyncStatsClient, spec_set=True)


# Create a TextChannel instance to get a realistic MagicMock of `discord.TextChannel`
channel_data = {
    "id": 1,
    "type": "TextChannel",
    "name": "channel",
    "parent_id": 1234567890,
    "topic": "topic",
    "position": 1,
    "nsfw": False,
    "last_message_id": 1,
    "bitrate": 1337,
    "user_limit": 25,
}
state = unittest.mock.MagicMock()
guild = unittest.mock.MagicMock()
text_channel_instance = discord.TextChannel(state=state, guild=guild, data=channel_data)

channel_data["type"] = "VoiceChannel"
voice_channel_instance = discord.VoiceChannel(state=state, guild=guild, data=channel_data)


class MockTextChannel(CustomMockMixin, unittest.mock.Mock, HashableMixin):
    """
    A MagicMock subclass to mock TextChannel objects.

    Instances of this class will follow the specifications of `discord.TextChannel` instances. For
    more information, see the `MockGuild` docstring.
    """
    spec_set = text_channel_instance

    def __init__(self, **kwargs) -> None:
        default_kwargs = {"id": next(self.discord_id), "name": "channel"}
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))

        if "mention" not in kwargs:
            self.mention = f"#{self.name}"

    @cached_property
    def guild(self) -> MockGuild:
        """Cached guild property."""
        return MockGuild()


class MockVoiceChannel(CustomMockMixin, unittest.mock.Mock, HashableMixin):
    """
    A MagicMock subclass to mock VoiceChannel objects.

    Instances of this class will follow the specifications of `discord.VoiceChannel` instances. For
    more information, see the `MockGuild` docstring.
    """
    spec_set = voice_channel_instance

    def __init__(self, **kwargs) -> None:
        default_kwargs = {"id": next(self.discord_id), "name": "channel"}
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))

        if "mention" not in kwargs:
            self.mention = f"#{self.name}"

    @cached_property
    def guild(self) -> MockGuild:
        """Cached guild property."""
        return MockGuild()


# Create data for the DMChannel instance
state = unittest.mock.MagicMock()
me = unittest.mock.MagicMock()
dm_channel_data = {"id": 1, "recipients": [unittest.mock.MagicMock()]}
dm_channel_instance = discord.DMChannel(me=me, state=state, data=dm_channel_data)


class MockDMChannel(CustomMockMixin, unittest.mock.Mock, HashableMixin):
    """
    A MagicMock subclass to mock DMChannel objects.

    Instances of this class will follow the specifications of `discord.DMChannel` instances. For
    more information, see the `MockGuild` docstring.
    """
    spec_set = dm_channel_instance

    def __init__(self, **kwargs) -> None:
        default_kwargs = {"id": next(self.discord_id), "recipient": MockUser(), "me": MockUser(), "guild": None}
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))


# Create CategoryChannel instance to get a realistic MagicMock of `discord.CategoryChannel`
category_channel_data = {
    "id": 1,
    "type": discord.ChannelType.category,
    "name": "category",
    "position": 1,
}

state = unittest.mock.MagicMock()
guild = unittest.mock.MagicMock()
category_channel_instance = discord.CategoryChannel(
    state=state, guild=guild, data=category_channel_data
)


class MockCategoryChannel(CustomMockMixin, unittest.mock.Mock, HashableMixin):
    def __init__(self, **kwargs) -> None:
        default_kwargs = {"id": next(self.discord_id)}
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))


# Create a Message instance to get a realistic MagicMock of `discord.Message`
message_data = {
    "id": 1,
    "webhook_id": 431341013479718912,
    "attachments": [],
    "embeds": [],
    "application": {"id": 4, "description": "A Python Bot", "name": "Python Discord", "icon": None},
    "activity": "mocking",
    "channel": unittest.mock.MagicMock(),
    "edited_timestamp": "2019-10-14T15:33:48+00:00",
    "type": "message",
    "pinned": False,
    "mention_everyone": False,
    "tts": None,
    "content": "content",
    "nonce": None,
}
state = unittest.mock.MagicMock()
channel = unittest.mock.MagicMock()
channel.type = discord.ChannelType.text
message_instance = discord.Message(state=state, channel=channel, data=message_data)


# Create a Context instance to get a realistic MagicMock of `discord.ext.commands.Context`
context_instance = Context(
    message=unittest.mock.MagicMock(),
    prefix="$",
    bot=MockBot(),
    view=None
)
context_instance.invoked_from_error_handler = None


class MockContext(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Context objects.

    Instances of this class will follow the specifications of `discord.ext.commands.Context`
    instances. For more information, see the `MockGuild` docstring.
    """
    spec_set = context_instance

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.me = kwargs.get("me", MockMember())
        self.bot = kwargs.get("bot", MockBot())

        self.message = kwargs.get("message", MockMessage(guild=self.guild))
        self.author = kwargs.get("author", self.message.author)
        self.channel = kwargs.get("channel", self.message.channel)
        self.guild = kwargs.get("guild", self.channel.guild)

        self.invoked_from_error_handler = kwargs.get("invoked_from_error_handler", False)


class MockInteraction(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Interaction objects.

    Instances of this class will follow the specifications of `discord.Interaction`
    instances. For more information, see the `MockGuild` docstring.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.me = kwargs.get("me", MockMember())
        self.client = kwargs.get("client", MockBot())

        self.message = kwargs.get("message", MockMessage(guild=self.guild))
        self.user = kwargs.get("user", self.message.author)
        self.channel = kwargs.get("channel", self.message.channel)
        self.guild = kwargs.get("guild", self.channel.guild)

        self.invoked_from_error_handler = kwargs.get("invoked_from_error_handler", False)


attachment_data = {
    "id": 1,
    "size": 14,
    "filename": "jchrist.png",
    "url": "https://google.com",
    "proxy_url": "https://google.com",
    "waveform": None,
}
attachment_instance = discord.Attachment(
    data=attachment_data,
    state=unittest.mock.MagicMock(),
)


class MockAttachment(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Attachment objects.

    Instances of this class will follow the specifications of `discord.Attachment` instances. For
    more information, see the `MockGuild` docstring.
    """
    spec_set = attachment_instance


message_reference_instance = discord.MessageReference(
    message_id=unittest.mock.MagicMock(id=1),
    channel_id=unittest.mock.MagicMock(id=2),
    guild_id=unittest.mock.MagicMock(id=3)
)


class MockMessageReference(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock MessageReference objects.

    Instances of this class will follow the specification of `discord.MessageReference` instances.
    For more information, see the `MockGuild` docstring.
    """
    spec_set = message_reference_instance

    def __init__(self, *, reference_author_is_bot: bool = False, **kwargs):
        super().__init__(**kwargs)
        referenced_msg_author = MockMember(name="bob", bot=reference_author_is_bot)
        self.resolved = MockMessage(author=referenced_msg_author)


class MockMessage(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Message objects.

    Instances of this class will follow the specifications of `discord.Message` instances. For more
    information, see the `MockGuild` docstring.
    """
    spec_set = message_instance

    def __init__(self, **kwargs) -> None:
        default_kwargs = {"attachments": []}
        super().__init__(**collections.ChainMap(kwargs, default_kwargs))
        self.author = kwargs.get("author", MockMember())
        self.channel = kwargs.get("channel", MockTextChannel())


class MockInteractionMessage(MockMessage):
    """
    A MagicMock subclass to mock InteractionMessage objects.

    Instances of this class will follow the specifications of `discord.InteractionMessage` instances. For more
    information, see the `MockGuild` docstring.
    """


emoji_data = {"require_colons": True, "managed": True, "id": 1, "name": "hyperlemon"}
emoji_instance = discord.Emoji(guild=MockGuild(), state=unittest.mock.MagicMock(), data=emoji_data)


class MockEmoji(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Emoji objects.

    Instances of this class will follow the specifications of `discord.Emoji` instances. For more
    information, see the `MockGuild` docstring.
    """
    spec_set = emoji_instance

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.guild = kwargs.get("guild", MockGuild())


partial_emoji_instance = discord.PartialEmoji(animated=False, name="guido")


class MockPartialEmoji(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock PartialEmoji objects.

    Instances of this class will follow the specifications of `discord.PartialEmoji` instances. For
    more information, see the `MockGuild` docstring.
    """
    spec_set = partial_emoji_instance


reaction_instance = discord.Reaction(message=MockMessage(), data={"me": True}, emoji=MockEmoji())


class MockReaction(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Reaction objects.

    Instances of this class will follow the specifications of `discord.Reaction` instances. For
    more information, see the `MockGuild` docstring.
    """
    spec_set = reaction_instance

    def __init__(self, **kwargs) -> None:
        _users = kwargs.pop("users", [])
        super().__init__(**kwargs)
        self.emoji = kwargs.get("emoji", MockEmoji())
        self.message = kwargs.get("message", MockMessage())

        user_iterator = unittest.mock.AsyncMock()
        user_iterator.__aiter__.return_value = _users
        self.users.return_value = user_iterator

        self.__str__.return_value = str(self.emoji)


webhook_instance = discord.Webhook(data=unittest.mock.MagicMock(), session=unittest.mock.MagicMock())


class MockAsyncWebhook(CustomMockMixin, unittest.mock.MagicMock):
    """
    A MagicMock subclass to mock Webhook objects using an AsyncWebhookAdapter.

    Instances of this class will follow the specifications of `discord.Webhook` instances. For
    more information, see the `MockGuild` docstring.
    """
    spec_set = webhook_instance
    additional_spec_asyncs = ("send", "edit", "delete", "execute")

@contextmanager
def no_create_task():
    def side_effect(coro, *_, **__):
        coro.close()

    with unittest.mock.patch("pydis_core.utils.scheduling.create_task") as create_task:
        create_task.side_effect = side_effect
        yield
