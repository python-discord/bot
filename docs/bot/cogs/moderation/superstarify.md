# Superstarify

> Auto-generated documentation for [bot.cogs.moderation.superstarify](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/superstarify.py) module.

- [Index](../../../README.md#modules) / [Bot](../../index.md#bot) / `Cogs` / [Moderation](index.md#moderation) / Superstarify
  - [Superstarify](#superstarify)
    - [Superstarify().modlog](#superstarifymodlog)
    - [Superstarify().cog_check](#superstarifycog_check)
    - [Superstarify.get_nick](#superstarifyget_nick)
    - [Superstarify().on_member_join](#superstarifyon_member_join)
    - [Superstarify().on_member_update](#superstarifyon_member_update)

## Superstarify

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/superstarify.py#L23)

```python
class Superstarify(bot: Bot)
```

A set of commands to moderate terrible nicknames.

### Superstarify().modlog

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/superstarify.py#L23)

```python
#property getter
def modlog() -> ModLog
```

Get currently loaded ModLog cog instance.

### Superstarify().cog_check

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/superstarify.py#L257)

```python
def cog_check(ctx: Context) -> bool
```

Only allow moderators to invoke the commands in this cog.

### Superstarify.get_nick

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/superstarify.py#L250)

```python
def get_nick(infraction_id: int, member_id: int) -> str
```

Randomly select a nickname from the Superstarify nickname list.

### Superstarify().on_member_join

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/superstarify.py#L89)

```python
def on_member_join(member: Member) -> None
```

This event will trigger when someone (re)joins the server.

At this point we will look up the user in our database and check whether they are in
superstar-prison. If so, we will change their name back to the forced nickname.

### Superstarify().on_member_update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/superstarify.py#L34)

```python
def on_member_update(before: Member, after: Member) -> None
```

This event will trigger when someone changes their name.

At this point we will look up the user in our database and check whether they are allowed to
change their names, or if they are in superstar-prison. If they are not allowed, we will
change it back.
