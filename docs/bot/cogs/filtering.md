# Filtering

> Auto-generated documentation for [bot.cogs.filtering](https://github.com/python-discord/bot/blob/master/bot/cogs/filtering.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Filtering
  - [Filtering](#filtering)
    - [Filtering().mod_log](#filteringmod_log)
    - [Filtering().notify_member](#filteringnotify_member)
    - [Filtering().on_message](#filteringon_message)
    - [Filtering().on_message_edit](#filteringon_message_edit)
  - [setup](#setup)

## Filtering

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/filtering.py#L40)

```python
class Filtering(bot: Bot)
```

Filtering out invites, blacklisting domains, and warning us of certain regular expressions.

### Filtering().mod_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/filtering.py#L40)

```python
#property getter
def mod_log() -> ModLog
```

Get currently loaded ModLog cog instance.

### Filtering().notify_member

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/filtering.py#L351)

```python
def notify_member(
    filtered_member: Member,
    reason: str,
    channel: TextChannel,
) -> None
```

Notify filtered_member about a moderation action with the reason str.

First attempts to DM the user, fall back to in-channel notification if user has DMs disabled

### Filtering().on_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/filtering.py#L105)

```python
def on_message(msg: Message) -> None
```

Invoke message filter for new messages.

### Filtering().on_message_edit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/filtering.py#L110)

```python
def on_message_edit(before: Message, after: Message) -> None
```

Invoke message filter for message edits.

If there have been multiple edits, calculate the time delta from the previous edit.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/filtering.py#L363)

```python
def setup(bot: Bot) -> None
```

Filtering cog load.
