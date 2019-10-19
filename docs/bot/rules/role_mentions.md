# Role Mentions

> Auto-generated documentation for [bot.rules.role_mentions](https://github.com/python-discord/bot/blob/master/bot/rules/role_mentions.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Rules](index.md#rules) / Role Mentions
  - [apply](#apply)

## apply

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/rules/role_mentions.py#L6)

```python
def apply(
    last_message: Message,
    recent_messages: List[discord.message.Message],
    config: Dict[str, int],
) -> Union[Tuple[str, Iterable[discord.member.Member], Iterable[discord.message.Message]], NoneType]
```

Detects total role mentions exceeding the limit sent by a single user.
