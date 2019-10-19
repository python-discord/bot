# Newlines

> Auto-generated documentation for [bot.rules.newlines](https://github.com/python-discord/bot/blob/master/bot/rules/newlines.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Rules](index.md#rules) / Newlines
  - [apply](#apply)

## apply

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/rules/newlines.py#L7)

```python
def apply(
    last_message: Message,
    recent_messages: List[discord.message.Message],
    config: Dict[str, int],
) -> Union[Tuple[str, Iterable[discord.member.Member], Iterable[discord.message.Message]], NoneType]
```

Detects total newlines exceeding the set limit sent by a single user.
