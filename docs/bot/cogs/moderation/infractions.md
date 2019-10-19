# Infractions

> Auto-generated documentation for [bot.cogs.moderation.infractions](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py) module.

- [Index](../../../README.md#modules) / [Bot](../../index.md#bot) / `Cogs` / [Moderation](index.md#moderation) / Infractions
  - [Infractions](#infractions)
    - [Infractions().description](#infractionsdescription)
    - [Infractions().mod_log](#infractionsmod_log)
    - [Infractions().qualified_name](#infractionsqualified_name)
    - [Infractions().apply_ban](#infractionsapply_ban)
    - [Infractions().apply_infraction](#infractionsapply_infraction)
    - [Infractions().apply_kick](#infractionsapply_kick)
    - [Infractions().apply_mute](#infractionsapply_mute)
    - [Infractions().cog_check](#infractionscog_check)
    - [Infractions().cog_command_error](#infractionscog_command_error)
    - [Infractions().deactivate_infraction](#infractionsdeactivate_infraction)
    - [Infractions().on_member_join](#infractionson_member_join)
    - [Infractions().pardon_infraction](#infractionspardon_infraction)
    - [Infractions().reschedule_infractions](#infractionsreschedule_infractions)

## Infractions

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L28)

```python
class Infractions(bot: Bot)
```

Apply and pardon infractions on users for moderation purposes.

### Infractions().description

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L28)

```python
#property getter
def description()
```

class `str`: Returns the cog's description, typically the cleaned docstring.

### Infractions().mod_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L28)

```python
#property getter
def mod_log() -> ModLog
```

Get currently loaded ModLog cog instance.

### Infractions().qualified_name

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L28)

```python
#property getter
def qualified_name()
```

class `str`: Returns the cog's specified name, not the class name.

### Infractions().apply_ban

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L162)

```python
def apply_ban(ctx: Context, args, kwargs) -> None
```

Apply a ban infraction with kwargs passed to `post_infraction`.

### Infractions().apply_infraction

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L421)

```python
def apply_infraction(
    ctx: Context,
    infraction: Dict[str, Union[str, int, bool]],
    user: Union[discord.member.Member, discord.user.User, discord.object.Object],
    action_coro: Union[Awaitable, NoneType] = None,
) -> None
```

Apply an infraction to the user, log the infraction, and optionally notify the user.

### Infractions().apply_kick

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L162)

```python
def apply_kick(ctx: Context, args, kwargs) -> None
```

Apply a kick infraction with kwargs passed to `post_infraction`.

### Infractions().apply_mute

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L238)

```python
def apply_mute(ctx: Context, user: Member, reason: str, kwargs) -> None
```

Apply a mute infraction with kwargs passed to `post_infraction`.

### Infractions().cog_check

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L597)

```python
def cog_check(ctx: Context) -> bool
```

Only allow moderators to invoke the commands in this cog.

### Infractions().cog_command_error

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L602)

```python
def cog_command_error(ctx: Context, error: Exception) -> None
```

Send a notification to the invoking context on a Union failure.

### Infractions().deactivate_infraction

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L297)

```python
def deactivate_infraction(
    infraction: Dict[str, Union[str, int, bool]],
    send_log: bool = True,
) -> Dict[str, str]
```

Deactivate an active infraction and return a dictionary of lines to send in a mod log.

The infraction is removed from Discord, marked as inactive in the database, and has its
expiration task cancelled. If `send_log` is True, a mod log is sent for the
deactivation of the infraction.

Supported infraction types are mute and ban. Other types will raise a ValueError.

### Infractions().on_member_join

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L60)

```python
def on_member_join(member: Member) -> None
```

Reapply active mute infractions for returning members.

### Infractions().pardon_infraction

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L503)

```python
def pardon_infraction(
    ctx: Context,
    infr_type: str,
    user: Union[discord.member.Member, discord.user.User, discord.object.Object],
) -> None
```

Prematurely end an infraction for a user and log the action in the mod log.

### Infractions().reschedule_infractions

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/infractions.py#L48)

```python
def reschedule_infractions() -> None
```

Schedule expiration for previous infractions.
