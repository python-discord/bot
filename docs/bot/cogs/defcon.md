# Defcon

> Auto-generated documentation for [bot.cogs.defcon](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Defcon
  - [Defcon](#defcon)
    - [Defcon().mod_log](#defconmod_log)
    - [Defcon().build_defcon_msg](#defconbuild_defcon_msg)
    - [Defcon().on_member_join](#defconon_member_join)
    - [Defcon().send_defcon_log](#defconsend_defcon_log)
    - [Defcon().sync_settings](#defconsync_settings)
    - [Defcon().update_channel_topic](#defconupdate_channel_topic)
  - [setup](#setup)

## Defcon

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py#L27)

```python
class Defcon(bot: Bot)
```

Time-sensitive server defense mechanisms.

### Defcon().mod_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py#L27)

```python
#property getter
def mod_log() -> ModLog
```

Get currently loaded ModLog cog instance.

### Defcon().build_defcon_msg

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py#L226)

```python
def build_defcon_msg(change: str, e: Exception = None) -> str
```

Build in-channel response string for DEFCON action.

`change` string may be one of the following: ('enabled', 'disabled', 'updated')

### Defcon().on_member_join

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py#L72)

```python
def on_member_join(member: Member) -> None
```

If DEFCON is enabled, check newly joining users to see if they meet the account age threshold.

### Defcon().send_defcon_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py#L250)

```python
def send_defcon_log(change: str, actor: Member, e: Exception = None) -> None
```

Send log message for DEFCON action.

`change` string may be one of the following: ('enabled', 'disabled', 'updated')

### Defcon().sync_settings

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py#L45)

```python
def sync_settings() -> None
```

On cog load, try to synchronize DEFCON settings to the API.

### Defcon().update_channel_topic

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py#L215)

```python
def update_channel_topic() -> None
```

Update the #defcon channel topic with the current DEFCON status.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/defcon.py#L282)

```python
def setup(bot: Bot) -> None
```

DEFCON cog load.
