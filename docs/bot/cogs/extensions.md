# Extensions

> Auto-generated documentation for [bot.cogs.extensions](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Extensions
  - [Action](#action)
  - [Extension](#extension)
    - [Extension().convert](#extensionconvert)
  - [Extensions](#extensions)
    - [Extensions().batch_manage](#extensionsbatch_manage)
    - [Extensions().cog_check](#extensionscog_check)
    - [Extensions().cog_command_error](#extensionscog_command_error)
    - [Extensions().manage](#extensionsmanage)
  - [setup](#setup)

## Action

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L25)

```python
class Action()
```

Represents an action to perform on an extension.

## Extension

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L34)

```python
class Extension()
```

Fully qualify the name of an extension and ensure it exists.

The * and ** values bypass this when used with the reload command.

### Extension().convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L41)

```python
def convert(ctx: Context, argument: str) -> str
```

Fully qualify the name of an extension and ensure it exists.

## Extensions

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L58)

```python
class Extensions(bot: Bot)
```

Extension management commands.

### Extensions().batch_manage

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L163)

```python
def batch_manage(action: Action, extensions: str) -> str
```

Apply an action to multiple extensions and return a message with the results.

If only one extension is given, it is deferred to `manage()`.

#### See also

- [Action](#action)

### Extensions().cog_check

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L221)

```python
def cog_check(ctx: Context) -> bool
```

Only allow moderators and core developers to invoke the commands in this cog.

### Extensions().cog_command_error

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L226)

```python
def cog_command_error(ctx: Context, error: Exception) -> None
```

Handle BadArgument errors locally to prevent the help command from showing.

### Extensions().manage

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L192)

```python
def manage(action: Action, ext: str) -> Tuple[str, Union[str, NoneType]]
```

Apply an action to an extension and return the status message and any error message.

#### See also

- [Action](#action)

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/extensions.py#L233)

```python
def setup(bot: Bot) -> None
```

Load the Extensions cog.
