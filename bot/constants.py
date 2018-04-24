# coding=utf-8
import logging
import os
from collections.abc import Mapping
from pathlib import Path

import yaml


log = logging.getLogger(__name__)


def _required_env_var_constructor(loader, node):
    value = loader.construct_scalar(node)
    return os.environ[value]


def _env_var_constructor(loader, node):
    value = loader.construct_scalar(node)
    return os.getenv(value)


yaml.SafeLoader.add_constructor('!REQUIRED_ENV', _required_env_var_constructor)
yaml.SafeLoader.add_constructor('!ENV', _env_var_constructor)


with open('config-example.yml') as f:
    _CONFIG_YAML = yaml.safe_load(f)


def _recursive_update(original, new):
    """
    Helper method which implements a recursive `dict.update`
    method, used for updating the original configuration with
    configuration specified by the user.
    """

    for key, value in original.items():
        if new.get(key) is None:
            continue

        if isinstance(value, Mapping):
            if not any(isinstance(subvalue, Mapping) for subvalue in value.values()):
                original[key].update(new[key])
            _recursive_update(original[key], new[key])
        else:
            original[key] = new[key]


if Path('config.yml').exists():
    log.info("Found `config.yml` file, loading constants from it.")
    with open('config.yml') as f:
        user_config = yaml.safe_load(f)
    _recursive_update(_CONFIG_YAML, user_config)


class YAMLGetter(type):
    subsection = None

    def __getattr__(cls, name):
        name = name.lower()

        if cls.subsection is not None:
            return _CONFIG_YAML[cls.section][cls.subsection][name]
        return _CONFIG_YAML[cls.section][name]

    def __getitem__(cls, name):
        return cls.__getattr__(name)


class Bot(metaclass=YAMLGetter):
    section = 'bot'


class Cooldowns(metaclass=YAMLGetter):
    section = 'bot'
    subsection = 'cooldowns'


class Emojis(metaclass=YAMLGetter):
    section = 'bot'
    subsection = 'emojis'


class Channels(metaclass=YAMLGetter):
    section = 'guild'
    subsection = 'channels'


class Roles(metaclass=YAMLGetter):
    section = 'guild'
    subsection = 'roles'


class Guild(metaclass=YAMLGetter):
    section = 'guild'


class Keys(metaclass=YAMLGetter):
    section = 'keys'


class ClickUp(metaclass=YAMLGetter):
    section = 'clickup'


class Papertrail(metaclass=YAMLGetter):
    section = 'papertrail'


class URLs(metaclass=YAMLGetter):
    section = 'urls'
