"""
Loads bot configuration from YAML files.
By default, this simply loads the default
configuration located at `config-default.yml`.
If a file called `config.yml` is found in the
project directory, the default configuration
is recursively updated with any settings from
the custom configuration. Any settings left
out in the custom user configuration will stay
their default values from `config-default.yml`.
"""

import logging
import os
from collections.abc import Mapping
from pathlib import Path

import yaml


log = logging.getLogger(__name__)


def _required_env_var_constructor(loader, node):
    """
    Implements a custom YAML tag for loading required environment
    variables. If the environment variable is set, this function
    will simply return it. Otherwise, a `CRITICAL` log message is
    given and the `KeyError` is re-raised.

    Example usage in the YAML configuration:

        bot:
            token: !REQUIRED_ENV 'BOT_TOKEN'
    """

    value = loader.construct_scalar(node)

    try:
        return os.environ[value]
    except KeyError:
        log.critical(
            f"Environment variable `{value}` is required, but was not set. "
            "Set it in your environment or override the option using it in your `config.yml`."
        )
        raise


def _env_var_constructor(loader, node):
    """
    Implements a custom YAML tag for loading optional environment
    variables. If the environment variable is set, returns the
    value of it. Otherwise, returns `None`.

    Example usage in the YAML configuration:

        # Optional app configuration. Set `MY_APP_KEY` in the environment to use it.
        application:
            key: !ENV 'MY_APP_KEY'
    """

    value = loader.construct_scalar(node)
    return os.getenv(value)


yaml.SafeLoader.add_constructor("!REQUIRED_ENV", _required_env_var_constructor)
yaml.SafeLoader.add_constructor("!ENV", _env_var_constructor)


with open("config-default.yml") as f:
    _CONFIG_YAML = yaml.safe_load(f)


def _recursive_update(original, new):
    """
    Helper method which implements a recursive `dict.update`
    method, used for updating the original configuration with
    configuration specified by the user.
    """

    for key, value in original.items():
        if key not in new:
            continue

        if isinstance(value, Mapping):
            if not any(isinstance(subvalue, Mapping) for subvalue in value.values()):
                original[key].update(new[key])
            _recursive_update(original[key], new[key])
        else:
            original[key] = new[key]


if Path("config.yml").exists():
    log.info("Found `config.yml` file, loading constants from it.")
    with open("config.yml") as f:
        user_config = yaml.safe_load(f)
    _recursive_update(_CONFIG_YAML, user_config)


class YAMLGetter(type):
    """
    Implements a custom metaclass used for accessing
    configuration data by simply accessing class attributes.
    Supports getting configuration from up to two levels
    of nested configuration through `section` and `subsection`.

    `section` specifies the YAML configuration section (or "key")
    in which the configuration lives, and must be set.

    `subsection` is an optional attribute specifying the section
    within the section from which configuration should be loaded.

    Example Usage:

        # config.yml
        bot:
            prefixes:
                direct_message: ''
                guild: '!'

        # config.py
        class Prefixes(metaclass=YAMLGetter):
            section = "bot"
            subsection = "prefixes"

        # Usage in Python code
        from config import Prefixes
        def get_prefix(bot, message):
            if isinstance(message.channel, PrivateChannel):
                return Prefixes.direct_message
            return Prefixes.guild
    """

    subsection = None

    def __getattr__(cls, name):
        name = name.lower()

        try:
            if cls.subsection is not None:
                return _CONFIG_YAML[cls.section][cls.subsection][name]
            return _CONFIG_YAML[cls.section][name]
        except KeyError:
            dotted_path = '.'.join(
                (cls.section, cls.subsection, name)
                if cls.subsection is not None else (cls.section, name)
            )
            log.critical(f"Tried accessing configuration variable at `{dotted_path}`, but it could not be found.")
            raise

    def __getitem__(cls, name):
        return cls.__getattr__(name)


class Bot(metaclass=YAMLGetter):
    section = "bot"


class Cooldowns(metaclass=YAMLGetter):
    section = "bot"
    subsection = "cooldowns"


class Emojis(metaclass=YAMLGetter):
    section = "bot"
    subsection = "emojis"


class Channels(metaclass=YAMLGetter):
    section = "guild"
    subsection = "channels"


class Roles(metaclass=YAMLGetter):
    section = "guild"
    subsection = "roles"


class Guild(metaclass=YAMLGetter):
    section = "guild"


class Keys(metaclass=YAMLGetter):
    section = "keys"


class ClickUp(metaclass=YAMLGetter):
    section = "clickup"


class Papertrail(metaclass=YAMLGetter):
    section = "papertrail"


class URLs(metaclass=YAMLGetter):
    section = "urls"
