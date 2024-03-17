from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
import types
import warnings
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from typing import Any, Self, TypeVar, Union, get_args, get_origin

import discord
import regex
from discord.ext.commands import Command
from pydantic import PydanticDeprecatedSince20
from pydantic_core import core_schema

import bot
from bot.bot import Bot
from bot.constants import Guild

VARIATION_SELECTORS = r"\uFE00-\uFE0F\U000E0100-\U000E01EF"
INVISIBLE_RE = regex.compile(rf"[{VARIATION_SELECTORS}\p{{UNASSIGNED}}\p{{FORMAT}}\p{{CONTROL}}--\s]", regex.V1)
ZALGO_RE = regex.compile(rf"[\p{{NONSPACING MARK}}\p{{ENCLOSING MARK}}--[{VARIATION_SELECTORS}]]", regex.V1)


T = TypeVar("T")

Serializable = bool | int | float | str | list | dict | None


def subclasses_in_package(package: str, prefix: str, parent: T) -> set[T]:
    """Return all the subclasses of class `parent`, found in the top-level of `package`, given by absolute path."""
    subclasses = set()

    # Find all modules in the package.
    for module_info in pkgutil.iter_modules([package], prefix):
        if not module_info.ispkg:
            module = importlib.import_module(module_info.name)
            # Find all classes in each module...
            for _, class_ in inspect.getmembers(module, inspect.isclass):
                # That are a subclass of the given class.
                if parent in class_.__mro__:
                    subclasses.add(class_)

    return subclasses


def clean_input(string: str) -> str:
    """Remove zalgo and invisible characters from `string`."""
    # For future consideration: remove characters in the Mc, Sk, and Lm categories too.
    # Can be normalised with form C to merge char + combining char into a single char to avoid
    # removing legit diacritics, but this would open up a way to bypass _filters.
    no_zalgo = ZALGO_RE.sub("", string)
    return INVISIBLE_RE.sub("", no_zalgo)


def past_tense(word: str) -> str:
    """Return the past tense form of the input word."""
    if not word:
        return word
    if word.endswith("e"):
        return word + "d"
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ied"
    return word + "ed"


def to_serializable(item: Any, *, ui_repr: bool = False) -> Serializable:
    """
    Convert the item into an object that can be converted to JSON.

    `ui_repr` dictates whether to use the UI representation of `CustomIOField` instances (if any)
    or the DB-oriented representation.
    """
    if isinstance(item, bool | int | float | str | type(None)):
        return item
    if isinstance(item, dict):
        result = {}
        for key, value in item.items():
            if not isinstance(key, bool | int | float | str | type(None)):
                key = str(key)
            result[key] = to_serializable(value, ui_repr=ui_repr)
        return result
    if isinstance(item, Iterable):
        return [to_serializable(subitem, ui_repr=ui_repr) for subitem in item]
    if not ui_repr and hasattr(item, "serialize"):
        return item.serialize()
    return str(item)


@cache
def resolve_mention(mention: str) -> str:
    """Return the appropriate formatting for the mention, be it a literal, a user ID, or a role ID."""
    guild = bot.instance.get_guild(Guild.id)
    if mention in ("here", "everyone"):
        return f"@{mention}"
    try:
        mention = int(mention)  # It's an ID.
    except ValueError:
        pass
    else:
        if any(mention == role.id for role in guild.roles):
            return f"<@&{mention}>"
        return f"<@{mention}>"

    # It's a name
    for role in guild.roles:
        if role.name == mention:
            return role.mention
    for member in guild.members:
        if str(member) == mention:
            return member.mention
    return mention


def repr_equals(override: Any, default: Any) -> bool:
    """Return whether the override and the default have the same representation."""
    if override is None:  # It's not an override
        return True

    override_is_sequence = isinstance(override, tuple | list | set)
    default_is_sequence = isinstance(default, tuple | list | set)
    if override_is_sequence != default_is_sequence:  # One is a sequence and the other isn't.
        return False
    if override_is_sequence:
        if len(override) != len(default):
            return False
        return all(str(item1) == str(item2) for item1, item2 in zip(set(override), set(default), strict=True))
    return str(override) == str(default)


def normalize_type(type_: type, *, prioritize_nonetype: bool = True) -> type:
    """Reduce a given type to one that can be initialized."""
    if get_origin(type_) in (Union, types.UnionType):  # In case of a Union
        args = get_args(type_)
        if type(None) in args:
            if prioritize_nonetype:
                return type(None)
            args = tuple(set(args) - {type(None)})
        type_ = args[0]  # Pick one, doesn't matter
    if origin := get_origin(type_):  # In case of a parameterized List, Set, Dict etc.
        return origin
    return type_


def starting_value(type_: type[T]) -> T:
    """Return a value of the given type."""
    type_ = normalize_type(type_)
    try:
        return type_()
    except TypeError:  # In case it all fails, return a string and let the user handle it.
        return ""


class FieldRequiring(ABC):
    """A mixin class that can force its concrete subclasses to set a value for specific class attributes."""

    # Sentinel value that mustn't remain in a concrete subclass.
    MUST_SET = object()

    # Sentinel value that mustn't remain in a concrete subclass.
    # Overriding value must be unique in the subclasses of the abstract class in which the attribute was set.
    MUST_SET_UNIQUE = object()

    # A mapping of the attributes which must be unique, and their unique values, per FieldRequiring subclass.
    __unique_attributes: defaultdict[type, dict[str, set]] = defaultdict(dict)

    @abstractmethod
    def __init__(self):
        ...

    def __init_subclass__(cls, **kwargs):
        def inherited(attr: str) -> bool:
            """True if `attr` was inherited from a parent class."""
            # The first element of cls.__mro__ is the class itself, last element is object, skip those.
            # hasattr(parent, attr) means the attribute was inherited.
            return any(hasattr(parent, attr) for parent in cls.__mro__[1:-1])

        # If a new attribute with the value MUST_SET_UNIQUE was defined in an abstract class, record it.
        if inspect.isabstract(cls):
            with warnings.catch_warnings():
                # The code below will raise a warning about the use the __fields__ attr on a pydantic model
                # This will continue to be warned about until removed in pydantic 3.0
                # This warning is a false-positive as only the custom MUST_SET_UNIQUE attr is used here
                warnings.simplefilter("ignore", category=PydanticDeprecatedSince20)
                for attribute in dir(cls):
                    if getattr(cls, attribute, None) is FieldRequiring.MUST_SET_UNIQUE:
                        if not inherited(attribute):
                            # A new attribute with the value MUST_SET_UNIQUE.
                            FieldRequiring.__unique_attributes[cls][attribute] = set()
            return

        for attribute in dir(cls):
            if attribute.startswith("__") or attribute in ("MUST_SET", "MUST_SET_UNIQUE"):
                continue
            value = getattr(cls, attribute)
            if value is FieldRequiring.MUST_SET and inherited(attribute):
                raise ValueError(f"You must set attribute {attribute!r} when creating {cls!r}")
            if value is FieldRequiring.MUST_SET_UNIQUE and inherited(attribute):
                raise ValueError(f"You must set a unique value to attribute {attribute!r} when creating {cls!r}")

            # Check if the value needs to be unique.
            for parent in cls.__mro__[1:-1]:
                # Find the parent class the attribute was first defined in.
                if attribute in FieldRequiring.__unique_attributes[parent]:
                    if value in FieldRequiring.__unique_attributes[parent][attribute]:
                        raise ValueError(f"Value of {attribute!r} in {cls!r} is not unique for parent {parent!r}.")

                    # Add to the set of unique values for that field.
                    FieldRequiring.__unique_attributes[parent][attribute].add(value)


@dataclass
class FakeContext:
    """
    A class representing a context-like object that can be sent to infraction commands.

    The goal is to be able to apply infractions without depending on the existence of a message or an interaction
    (which are the two ways to create a Context), e.g. in API events which aren't message-driven, or in custom filtering
    events.
    """

    message: discord.Message
    channel: discord.abc.Messageable
    command: Command | None
    bot: Bot | None = None
    guild: discord.Guild | None = None
    author: discord.Member | discord.User | None = None
    me: discord.Member | None = None

    def __post_init__(self):
        """Initialize the missing information."""
        if not self.bot:
            self.bot = bot.instance
        if not self.guild:
            self.guild = self.bot.get_guild(Guild.id)
        if not self.me:
            self.me = self.guild.me
        if not self.author:
            self.author = self.me

    async def send(self, *args, **kwargs) -> discord.Message:
        """A wrapper for channel.send."""
        return await self.channel.send(*args, **kwargs)


class CustomIOField:
    """
    A class to be used as a data type in SettingEntry subclasses.

    Its subclasses can have custom methods to read and represent the value, which will be used by the UI.
    """

    def __init__(self, value: Any):
        self.value = self.process_value(value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source: type[Any],
        _handler: Callable[[Any], core_schema.CoreSchema],
    ) -> core_schema.CoreSchema:
        """Boilerplate for Pydantic."""
        return core_schema.with_info_plain_validator_function(cls.validate)

    @classmethod
    def validate(cls, v: Any, _info: core_schema.ValidationInfo) -> Self:
        """Takes the given value and returns a class instance with that value."""
        if isinstance(v, CustomIOField):
            return cls(v.value)

        return cls(v)

    def __eq__(self, other: CustomIOField):
        if not isinstance(other, CustomIOField):
            return NotImplemented
        return self.value == other.value

    @classmethod
    def process_value(cls, v: str) -> Any:
        """
        Perform any necessary transformations before the value is stored in a new instance.

        Override this method to customize the input behavior.
        """
        return v

    def serialize(self) -> Serializable:
        """Override this method to customize how the value will be serialized."""
        return self.value

    def __str__(self):
        """Override this method to change how the value will be displayed by the UI."""
        return self.value
