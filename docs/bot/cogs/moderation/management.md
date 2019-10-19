# Management

> Auto-generated documentation for [bot.cogs.moderation.management](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py) module.

- [Index](../../../README.md#modules) / [Bot](../../index.md#bot) / `Cogs` / [Moderation](index.md#moderation) / Management
  - [ModManagement](#modmanagement)
    - [ModManagement().infractions_cog](#modmanagementinfractions_cog)
    - [ModManagement().mod_log](#modmanagementmod_log)
    - [ModManagement().cog_check](#modmanagementcog_check)
    - [ModManagement().cog_command_error](#modmanagementcog_command_error)
    - [ModManagement().infraction_to_string](#modmanagementinfraction_to_string)
    - [ModManagement().send_infraction_list](#modmanagementsend_infraction_list)
  - [permanent_duration](#permanent_duration)

## ModManagement

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py#L33)

```python
class ModManagement(bot: Bot)
```

Management of infractions.

### ModManagement().infractions_cog

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py#L33)

```python
#property getter
def infractions_cog() -> Infractions
```

Get currently loaded Infractions cog instance.

### ModManagement().mod_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py#L33)

```python
#property getter
def mod_log() -> ModLog
```

Get currently loaded ModLog cog instance.

### ModManagement().cog_check

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py#L258)

```python
def cog_check(ctx: Context) -> bool
```

Only allow moderators to invoke the commands in this cog.

### ModManagement().cog_command_error

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py#L263)

```python
def cog_command_error(ctx: Context, error: Exception) -> None
```

Send a notification to the invoking context on a Union failure.

### ModManagement().infraction_to_string

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py#L225)

```python
def infraction_to_string(infraction: Dict[str, Union[str, int, bool]]) -> str
```

Convert the infraction object to a string representation.

### ModManagement().send_infraction_list

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py#L200)

```python
def send_infraction_list(
    ctx: Context,
    embed: Embed,
    infractions: Iterable[Dict[str, Union[str, int, bool]]],
) -> None
```

Send a paginated embed of infractions for the specified user.

## permanent_duration

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/management.py#L24)

```python
def permanent_duration(expires_at: str) -> str
```

Only allow an expiration to be 'permanent' if it is a string.
