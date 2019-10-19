# message_edited_at patch.

> Auto-generated documentation for [bot.patches.message_edited_at](https://github.com/python-discord/bot/blob/master/bot/patches/message_edited_at.py) module.

Date: 2019-09-16
Author: Scragly
Added by: Ves Zappa

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Patches](index.md#patches) / message_edited_at patch.
  - [_handle_edited_timestamp](#_handle_edited_timestamp)
  - [apply_patch](#apply_patch)

Due to a bug in our current version of discord.py (1.2.3), the edited_at timestamp of
`discord.Messages` are not being handled correctly. This patch fixes that until a new
release of discord.py is released (and we've updated to it).

## _handle_edited_timestamp

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/patches/message_edited_at.py#L19)

```python
def _handle_edited_timestamp(value: str) -> None
```

Helper function that takes care of parsing the edited timestamp.

## apply_patch

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/patches/message_edited_at.py#L24)

```python
def apply_patch() -> None
```

Applies the `edited_at` patch to the `discord.message.Message` class.
