# ErrorHandler

> Auto-generated documentation for [bot.cogs.error_handler](https://github.com/python-discord/bot/blob/master/bot/cogs/error_handler.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / ErrorHandler
  - [ErrorHandler](#errorhandler)
    - [ErrorHandler.handle_unexpected_error](#errorhandlerhandle_unexpected_error)
    - [ErrorHandler().on_command_error](#errorhandleron_command_error)
  - [setup](#setup)

## ErrorHandler

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/error_handler.py#L26)

```python
class ErrorHandler(bot: Bot)
```

Handles errors emitted from commands.

### ErrorHandler.handle_unexpected_error

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/error_handler.py#L132)

```python
def handle_unexpected_error(ctx: Context, e: CommandError) -> None
```

Generic handler for errors without an explicit handler.

### ErrorHandler().on_command_error

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/error_handler.py#L32)

```python
def on_command_error(ctx: Context, e: CommandError) -> None
```

Provide generic command error handling.

Error handling is deferred to any local error handler, if present.

Error handling emits a single error response, prioritized as follows:
    1. If the name fails to match a command but matches a tag, the tag is invoked
    2. Send a BadArgument error message to the invoking context & invoke the command's help
    3. Send a UserInputError error message to the invoking context & invoke the command's help
    4. Send a NoPrivateMessage error message to the invoking context
    5. Send a BotMissingPermissions error message to the invoking context
    6. Log a MissingPermissions error, no message is sent
    7. Send a InChannelCheckFailure error message to the invoking context
    8. Log CheckFailure, CommandOnCooldown, and DisabledCommand errors, no message is sent
    9. For CommandInvokeErrors, response is based on the type of error:
        * 404: Error message is sent to the invoking context
        * 400: Log the resopnse JSON, no message is sent
        * 500 <= status <= 600: Error message is sent to the invoking context
    10. Otherwise, handling is deferred to `handle_unexpected_error`

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/error_handler.py#L145)

```python
def setup(bot: Bot) -> None
```

Error handler cog load.
