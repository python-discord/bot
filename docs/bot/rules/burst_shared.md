# Burst Shared

> Auto-generated documentation for [bot.rules.burst_shared](https://github.com/python-discord/bot/blob/master/bot/rules/burst_shared.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Rules](index.md#rules) / Burst Shared
  - [apply](#apply)

## apply

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/rules/burst_shared.py#L6)

```python
def apply(
    last_message: Message,
    recent_messages: List[discord.message.Message],
    config: Dict[str, int],
) -> Union[Tuple[str, Iterable[discord.member.Member], Iterable[discord.message.Message]], NoneType]
```

Detects repeated messages sent by multiple users.
