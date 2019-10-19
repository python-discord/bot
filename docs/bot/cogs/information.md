# Information

> Auto-generated documentation for [bot.cogs.information](https://github.com/python-discord/bot/blob/master/bot/cogs/information.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Information
  - [Information](#information)
    - [Information().format_fields](#informationformat_fields)
  - [setup](#setup)

## Information

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/information.py#L21)

```python
class Information(bot: Bot)
```

A cog with commands for generating embeds with server info, such as server stats and user info.

### Information().format_fields

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/information.py#L236)

```python
def format_fields(
    mapping: Mapping[str, Any],
    field_width: Union[int, NoneType] = None,
) -> str
```

Format a mapping to be readable to a human.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/information.py#L313)

```python
def setup(bot: Bot) -> None
```

Information cog load.
