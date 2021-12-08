import importlib
import importlib.util
import inspect
import pkgutil
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Set

import regex

from bot.constants import Roles

ROLE_LITERALS = {
    "admins": Roles.admins,
    "onduty": Roles.moderators,
    "staff": Roles.helpers
}

VARIATION_SELECTORS = r"\uFE00-\uFE0F\U000E0100-\U000E01EF"
INVISIBLE_RE = regex.compile(rf"[{VARIATION_SELECTORS}\p{{UNASSIGNED}}\p{{FORMAT}}\p{{CONTROL}}--\s]", regex.V1)
ZALGO_RE = regex.compile(rf"[\p{{NONSPACING MARK}}\p{{ENCLOSING MARK}}--[{VARIATION_SELECTORS}]]", regex.V1)


def subclasses_in_package(package: str, prefix: str, parent: type) -> Set[type]:
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
        # If a new attribute with the value MUST_SET_UNIQUE was defined in an abstract class, record it.
        if inspect.isabstract(cls):
            for attribute in dir(cls):
                if getattr(cls, attribute, None) is FieldRequiring.MUST_SET_UNIQUE:
                    for parent in cls.__mro__[1:-1]:  # The first element is the class itself, last element is object.
                        if hasattr(parent, attribute):  # The attribute was inherited.
                            break
                    else:
                        # A new attribute with the value MUST_SET_UNIQUE.
                        FieldRequiring.__unique_attributes[cls][attribute] = set()
            return

        for attribute in dir(cls):
            if attribute.startswith("__") or attribute in ("MUST_SET", "MUST_SET_UNIQUE"):
                continue
            value = getattr(cls, attribute)
            if value is FieldRequiring.MUST_SET:
                raise ValueError(f"You must set attribute {attribute!r} when creating {cls!r}")
            elif value is FieldRequiring.MUST_SET_UNIQUE:
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
