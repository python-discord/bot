# Clean

> Auto-generated documentation for [bot.cogs.clean](https://github.com/python-discord/bot/blob/master/bot/cogs/clean.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Clean
  - [Clean](#clean)
    - [Clean().mod_log](#cleanmod_log)
  - [setup](#setup)

## Clean

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/clean.py#L19)

```python
class Clean(bot: Bot)
```

A cog that allows messages to be deleted in bulk, while applying various filters.

You can delete messages sent by a specific user, messages sent by bots, all messages, or messages that match a
specific regular expression.

The deleted messages are saved and uploaded to the database via an API endpoint, and a URL is returned which can be
used to view the messages in the Discord dark theme style.

### Clean().mod_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/clean.py#L19)

```python
#property getter
def mod_log() -> ModLog
```

Get currently loaded ModLog cog instance.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/clean.py#L213)

```python
def setup(bot: Bot) -> None
```

Clean cog load.
