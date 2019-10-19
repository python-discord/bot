# Syncers

> Auto-generated documentation for [bot.cogs.sync.syncers](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py) module.

- [Index](../../../README.md#modules) / [Bot](../../index.md#bot) / `Cogs` / [Sync](index.md#sync) / Syncers
  - [Role](#role)
    - [Role().colour](#rolecolour)
    - [Role().id](#roleid)
    - [Role().name](#rolename)
    - [Role().permissions](#rolepermissions)
    - [Role().position](#roleposition)
  - [User](#user)
    - [User().avatar_hash](#useravatar_hash)
    - [User().discriminator](#userdiscriminator)
    - [User().id](#userid)
    - [User().in_guild](#userin_guild)
    - [User().name](#username)
    - [User().roles](#userroles)
  - [get_roles_for_sync](#get_roles_for_sync)
  - [get_users_for_sync](#get_users_for_sync)
  - [sync_roles](#sync_roles)
  - [sync_users](#sync_users)

## Role

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
class Role()
```

Role(id, name, colour, permissions, position)

### Role().colour

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(2)()
```

Alias for field number 2

### Role().id

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(0)()
```

Alias for field number 0

### Role().name

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(1)()
```

Alias for field number 1

### Role().permissions

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(3)()
```

Alias for field number 3

### Role().position

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(4)()
```

Alias for field number 4

## User

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
class User()
```

User(id, name, discriminator, avatar_hash, roles, in_guild)

### User().avatar_hash

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(3)()
```

Alias for field number 3

### User().discriminator

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(2)()
```

Alias for field number 2

### User().id

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(0)()
```

Alias for field number 0

### User().in_guild

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(5)()
```

Alias for field number 5

### User().name

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(1)()
```

Alias for field number 1

### User().roles

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L1)

```python
#property getter
def operator.itemgetter(4)()
```

Alias for field number 4

## get_roles_for_sync

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L13)

```python
def get_roles_for_sync(
    guild_roles: Set[bot.cogs.sync.syncers.Role],
    api_roles: Set[bot.cogs.sync.syncers.Role],
) -> Tuple[Set[bot.cogs.sync.syncers.Role], Set[bot.cogs.sync.syncers.Role], Set[bot.cogs.sync.syncers.Role]]
```

Determine which roles should be created or updated on the site.

#### Arguments

guild_roles (Set[Role]):
    Roles that were found on the guild at startup.

api_roles (Set[Role]):
    Roles that were retrieved from the API at startup.

#### Returns

Tuple[Set[Role], Set[Role]. Set[Role]]:
    A tuple with three elements. The first element represents
    roles to be created on the site, meaning that they were
    present on the cached guild but not on the API. The second
    element represents roles to be updated, meaning they were
    present on both the cached guild and the API but non-ID
    fields have changed inbetween. The third represents roles
    to be deleted on the site, meaning the roles are present on
    the API but not in the cached guild.

#### See also

- [Role](#role)

## get_users_for_sync

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L114)

```python
def get_users_for_sync(
    guild_users: Dict[int, bot.cogs.sync.syncers.User],
    api_users: Dict[int, bot.cogs.sync.syncers.User],
) -> Tuple[Set[bot.cogs.sync.syncers.User], Set[bot.cogs.sync.syncers.User]]
```

Determine which users should be created or updated on the website.

#### Arguments

guild_users (Dict[int, User]):
    A mapping of user IDs to user data, populated from the
    guild cached on the running bot instance.

api_users (Dict[int, User]):
    A mapping of user IDs to user data, populated from the API's
    current inventory of all users.

#### Returns

Tuple[Set[User], Set[User]]:
    Two user sets as a tuple. The first element represents users
    to be created on the website, these are users that are present
    in the cached guild data but not in the API at all, going by
    their ID. The second element represents users to update. It is
    populated by users which are present on both the API and the
    guild, but where the attribute of a user on the API is not
    equal to the attribute of the user on the guild.

#### See also

- [User](#user)

## sync_roles

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L50)

```python
def sync_roles(bot: Bot, guild: Guild) -> Tuple[int, int, int]
```

Synchronize roles found on the given `guild` with the ones on the API.

#### Arguments

bot (discord.ext.commands.Bot):
    The bot instance that we're running with.

guild (discord.Guild):
    The guild instance from the bot's cache
    to synchronize roles with.

#### Returns

Tuple[int, int, int]:
    A tuple with three integers representing how many roles were created
    (element `0`) , how many roles were updated (element `1`), and how many
    roles were deleted (element `2`) on the API.

## sync_users

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/syncers.py#L167)

```python
def sync_users(bot: Bot, guild: Guild) -> Tuple[int, int, NoneType]
```

Synchronize users found in the given `guild` with the ones in the API.

#### Arguments

bot (discord.ext.commands.Bot):
    The bot instance that we're running with.

guild (discord.Guild):
    The guild instance from the bot's cache
    to synchronize roles with.

#### Returns

Tuple[int, int, None]:
    A tuple with two integers, representing how many users were created
    (element `0`) and how many users were updated (element `1`), and `None`
    to indicate that a user sync never deletes entries from the API.
