# Duplicates

> Auto-generated documentation for [bot.rules.duplicates](https://github.com/python-discord/bot/blob/master/bot/rules/duplicates.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Rules](index.md#rules) / Duplicates
  - [apply](#apply)

## apply

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/rules/duplicates.py#L6)

```python
def apply(
    last_message: Message,
    recent_messages: List[discord.message.Message],
    config: Dict[str, int],
) -> Union[Tuple[str, Iterable[discord.member.Member], Iterable[discord.message.Message]], NoneType]
```

Detects duplicated messages sent by a single user.
