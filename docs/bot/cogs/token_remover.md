# TokenRemover

> Auto-generated documentation for [bot.cogs.token_remover](https://github.com/python-discord/bot/blob/master/bot/cogs/token_remover.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / TokenRemover
  - [TokenRemover](#tokenremover)
    - [TokenRemover().mod_log](#tokenremovermod_log)
    - [TokenRemover.is_valid_timestamp](#tokenremoveris_valid_timestamp)
    - [TokenRemover.is_valid_user_id](#tokenremoveris_valid_user_id)
    - [TokenRemover().on_message](#tokenremoveron_message)
  - [setup](#setup)

## TokenRemover

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/token_remover.py#L37)

```python
class TokenRemover(bot: Bot)
```

Scans messages for potential discord.py bot tokens and removes them.

### TokenRemover().mod_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/token_remover.py#L37)

```python
#property getter
def mod_log() -> ModLog
```

Get currently loaded ModLog cog instance.

### TokenRemover.is_valid_timestamp

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/token_remover.py#L104)

```python
def is_valid_timestamp(b64_content: str) -> bool
```

Check potential token to see if it contains a valid timestamp.

See: https://discordapp.com/developers/docs/reference#snowflakes

### TokenRemover.is_valid_user_id

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/token_remover.py#L89)

```python
def is_valid_user_id(b64_content: str) -> bool
```

Check potential token to see if it contains a valid Discord user ID.

See: https://discordapp.com/developers/docs/reference#snowflakes

### TokenRemover().on_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/token_remover.py#L48)

```python
def on_message(msg: Message) -> None
```

Check each message for a string that matches Discord's token pattern.

See: https://discordapp.com/developers/docs/reference#snowflakes

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/token_remover.py#L121)

```python
def setup(bot: Bot) -> None
```

Token Remover cog load.
