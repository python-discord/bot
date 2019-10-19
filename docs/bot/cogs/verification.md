# Verification

> Auto-generated documentation for [bot.cogs.verification](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Verification
  - [Verification](#verification)
    - [Verification().mod_log](#verificationmod_log)
    - [Verification().before_ping](#verificationbefore_ping)
    - [Verification.bot_check](#verificationbot_check)
    - [Verification().cog_command_error](#verificationcog_command_error)
    - [Verification().cog_unload](#verificationcog_unload)
    - [Verification().on_message](#verificationon_message)
  - [setup](#setup)

## Verification

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py#L38)

```python
class Verification(bot: Bot)
```

User verification and role self-management.

### Verification().mod_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py#L38)

```python
#property getter
def mod_log() -> ModLog
```

Get currently loaded ModLog cog instance.

### Verification().before_ping

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py#L185)

```python
def before_ping() -> None
```

Only start the loop when the bot is ready.

### Verification.bot_check

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py#L158)

```python
def bot_check(ctx: Context) -> bool
```

Block any command within the verification channel that is not !accept.

### Verification().cog_command_error

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py#L153)

```python
def cog_command_error(ctx: Context, error: Exception) -> None
```

Check for & ignore any InChannelCheckFailure.

### Verification().cog_unload

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py#L190)

```python
def cog_unload() -> None
```

Cancel the periodic ping task when the cog is unloaded.

### Verification().on_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py#L50)

```python
def on_message(message: Context) -> None
```

Check new message event for messages to the checkpoint channel & process.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/verification.py#L195)

```python
def setup(bot: Bot) -> None
```

Verification cog load.
