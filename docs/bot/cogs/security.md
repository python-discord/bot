# Security

> Auto-generated documentation for [bot.cogs.security](https://github.com/python-discord/bot/blob/master/bot/cogs/security.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Security
  - [Security](#security)
    - [Security().check_not_bot](#securitycheck_not_bot)
    - [Security().check_on_guild](#securitycheck_on_guild)
  - [setup](#setup)

## Security

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/security.py#L8)

```python
class Security(bot: Bot)
```

Security-related helpers.

### Security().check_not_bot

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/security.py#L16)

```python
def check_not_bot(ctx: Context) -> bool
```

Check if the context is a bot user.

### Security().check_on_guild

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/security.py#L20)

```python
def check_on_guild(ctx: Context) -> bool
```

Check if the context is in a guild.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/security.py#L27)

```python
def setup(bot: Bot) -> None
```

Security cog load.
