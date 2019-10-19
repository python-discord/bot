# Constants

> Auto-generated documentation for [bot.constants](https://github.com/python-discord/bot/blob/master/bot/constants.py) module.

Loads bot configuration from YAML files.
By default, this simply loads the default
configuration located at `config-default.yml`.
If a file called `config.yml` is found in the
project directory, the default configuration
is recursively updated with any settings from
the custom configuration. Any settings left
out in the custom user configuration will stay
their default values from `config-default.yml`.

- [Index](../README.md#modules) / [Bot](index.md#bot) / Constants
  - [AntiSpam](#antispam)
  - [BigBrother](#bigbrother)
  - [Bot](#bot)
  - [Categories](#categories)
  - [Channels](#channels)
  - [CleanMessages](#cleanmessages)
  - [Colours](#colours)
  - [Cooldowns](#cooldowns)
  - [Emojis](#emojis)
  - [Event](#event)
  - [Filter](#filter)
  - [Free](#free)
  - [Guild](#guild)
  - [Icons](#icons)
  - [Keys](#keys)
  - [Mention](#mention)
  - [Reddit](#reddit)
  - [RedirectOutput](#redirectoutput)
  - [Roles](#roles)
  - [URLs](#urls)
  - [Webhooks](#webhooks)
  - [Wolfram](#wolfram)
  - [YAMLGetter](#yamlgetter)
  - [_env_var_constructor](#_env_var_constructor)
  - [_join_var_constructor](#_join_var_constructor)
  - [_recursive_update](#_recursive_update)
  - [check_required_keys](#check_required_keys)

## AntiSpam

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L453)

```python
class AntiSpam()
```

## BigBrother

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L463)

```python
class BigBrother()
```

## Bot

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L191)

```python
class Bot()
```

## Categories

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L319)

```python
class Categories()
```

## Channels

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L326)

```python
class Channels()
```

## CleanMessages

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L312)

```python
class CleanMessages()
```

## Colours

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L230)

```python
class Colours()
```

## Cooldowns

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L223)

```python
class Cooldowns()
```

## Emojis

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L239)

```python
class Emojis()
```

## Event

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L559)

```python
class Event()
```

Event names. This does not include every event (for example, raw
events aren't here), but only events used in ModLog for now.

## Filter

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L198)

```python
class Filter()
```

## Free

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L470)

```python
class Free()
```

## Guild

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L389)

```python
class Guild()
```

## Icons

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L263)

```python
class Icons()
```

## Keys

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L396)

```python
class Keys()
```

## Mention

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L478)

```python
class Mention()
```

## Reddit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L438)

```python
class Reddit()
```

## RedirectOutput

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L485)

```python
class RedirectOutput()
```

## Roles

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L369)

```python
class Roles()
```

## URLs

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L402)

```python
class URLs()
```

## Webhooks

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L361)

```python
class Webhooks()
```

## Wolfram

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L445)

```python
class Wolfram()
```

## YAMLGetter

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L135)

```python
class YAMLGetter()
```

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

## _env_var_constructor

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L25)

```python
def _env_var_constructor(loader, node)
```

Implements a custom YAML tag for loading optional environment
variables. If the environment variable is set, returns the
value of it. Otherwise, returns `None`.

Example usage in the YAML configuration:

# Optional app configuration. Set `MY_APP_KEY` in the environment to use it.
application:
    key: !ENV 'MY_APP_KEY'

## _join_var_constructor

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L59)

```python
def _join_var_constructor(loader, node)
```

Implements a custom YAML tag for concatenating other tags in
the document to strings. This allows for a much more DRY configuration
file.

## _recursive_update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L81)

```python
def _recursive_update(original, new)
```

Helper method which implements a recursive `dict.update`
method, used for updating the original configuration with
configuration specified by the user.

## check_required_keys

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/constants.py#L107)

```python
def check_required_keys(keys)
```

Verifies that keys that are set to be required are present in the
loaded configuration.
