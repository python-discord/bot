import importlib
import importlib.util
import inspect
import pkgutil
from abc import ABC, abstractmethod
from collections import defaultdict
from functools import cache
from typing import Any, Iterable, TypeVar, Union

import regex

import bot
from bot.constants import Guild

VARIATION_SELECTORS = r"\uFE00-\uFE0F\U000E0100-\U000E01EF"
INVISIBLE_RE = regex.compile(rf"[{VARIATION_SELECTORS}\p{{UNASSIGNED}}\p{{FORMAT}}\p{{CONTROL}}--\s]", regex.V1)
ZALGO_RE = regex.compile(rf"[\p{{NONSPACING MARK}}\p{{ENCLOSING MARK}}--[{VARIATION_SELECTORS}]]", regex.V1)


T = TypeVar('T')


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
                if parent in class_.__bases__:
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


def to_serializable(item: Any) -> Union[bool, int, float, str, list, dict, None]:
    """Convert the item into an object that can be converted to JSON."""
    if isinstance(item, (bool, int, float, str, type(None))):
        return item
    if isinstance(item, dict):
        result = {}
        for key, value in item.items():
            if not isinstance(key, (bool, int, float, str, type(None))):
                key = str(key)
            result[key] = to_serializable(value)
        return result
    if isinstance(item, Iterable):
        return [to_serializable(subitem) for subitem in item]
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
        else:
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

    override_is_sequence = isinstance(override, (tuple, list, set))
    default_is_sequence = isinstance(default, (tuple, list, set))
    if override_is_sequence != default_is_sequence:  # One is a sequence and the other isn't.
        return False
    if override_is_sequence:
        if len(override) != len(default):
            return False
        return all(str(item1) == str(item2) for item1, item2 in zip(set(override), set(default)))
    return str(override) == str(default)


def starting_value(type_: type[T]) -> T:
    """Return a value of the given type."""
    if hasattr(type_, "__origin__"):
        if type_.__origin__ is not Union:  # In case this is a types.GenericAlias or a typing._GenericAlias
            type_ = type_.__origin__
    if hasattr(type_, "__args__"):  # In case of a Union
        if type(None) in type_.__args__:
            return None
        type_ = type_.__args__[0]  # Pick one, doesn't matter

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
            for parent in cls.__mro__[1:-1]:  # The first element is the class itself, last element is object.
                if hasattr(parent, attr):  # The attribute was inherited.
                    return True
            return False

        # If a new attribute with the value MUST_SET_UNIQUE was defined in an abstract class, record it.
        if inspect.isabstract(cls):
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
            elif value is FieldRequiring.MUST_SET_UNIQUE and inherited(attribute):
                raise ValueError(f"You must set a unique value to attribute {attribute!r} when creating {cls!r}")
            else:
                # Check if the value needs to be unique.
                for parent in cls.__mro__[1:-1]:
                    # Find the parent class the attribute was first defined in.
                    if attribute in FieldRequiring.__unique_attributes[parent]:
                        if value in FieldRequiring.__unique_attributes[parent][attribute]:
                            raise ValueError(f"Value of {attribute!r} in {cls!r} is not unique for parent {parent!r}.")
                        else:
                            # Add to the set of unique values for that field.
                            FieldRequiring.__unique_attributes[parent][attribute].add(value)
