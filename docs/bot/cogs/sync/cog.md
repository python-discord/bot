# Cog

> Auto-generated documentation for [bot.cogs.sync.cog](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py) module.

- [Index](../../../README.md#modules) / [Bot](../../index.md#bot) / `Cogs` / [Sync](index.md#sync) / Cog
  - [Sync](#sync)
    - [Sync().on_guild_role_create](#syncon_guild_role_create)
    - [Sync().on_guild_role_delete](#syncon_guild_role_delete)
    - [Sync().on_guild_role_update](#syncon_guild_role_update)
    - [Sync().on_member_join](#syncon_member_join)
    - [Sync().on_member_remove](#syncon_member_remove)
    - [Sync().on_member_update](#syncon_member_update)
    - [Sync().sync_guild](#syncsync_guild)

## Sync

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py#L15)

```python
class Sync(bot: Bot) -> None
```

Captures relevant events and sends them to the site.

### Sync().on_guild_role_create

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py#L53)

```python
def on_guild_role_create(role: Role) -> None
```

Adds newly create role to the database table over the API.

### Sync().on_guild_role_delete

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py#L67)

```python
def on_guild_role_delete(role: Role) -> None
```

Deletes role from the database when it's deleted from the guild.

### Sync().on_guild_role_update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py#L72)

```python
def on_guild_role_update(before: Role, after: Role) -> None
```

Syncs role with the database if any of the stored attributes were updated.

### Sync().on_member_join

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py#L92)

```python
def on_member_join(member: Member) -> None
```

Adds a new user or updates existing user to the database when a member joins the guild.

If the joining member is a user that is already known to the database (i.e., a user that
previously left), it will update the user's information. If the user is not yet known by
the database, the user is added.

### Sync().on_member_remove

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py#L128)

```python
def on_member_remove(member: Member) -> None
```

Updates the user information when a member leaves the guild.

### Sync().on_member_update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py#L143)

```python
def on_member_update(before: Member, after: Member) -> None
```

Updates the user information if any of relevant attributes have changed.

### Sync().sync_guild

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/sync/cog.py#L34)

```python
def sync_guild() -> None
```

Syncs the roles/users of the guild with the database.
