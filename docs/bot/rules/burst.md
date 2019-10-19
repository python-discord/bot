# Burst

> Auto-generated documentation for [bot.rules.burst](https://github.com/python-discord/bot/blob/master/bot/rules/burst.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Rules](index.md#rules) / Burst
  - [apply](#apply)
  - Modules
    - [Burst Shared](burst_shared.md#burst-shared)

## apply

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/rules/burst.py#L6)

```python
def apply(
    last_message: Message,
    recent_messages: List[discord.message.Message],
    config: Dict[str, int],
) -> Union[Tuple[str, Iterable[discord.member.Member], Iterable[discord.message.Message]], NoneType]
```

Detects repeated messages sent by a single user.
