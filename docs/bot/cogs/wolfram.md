# Wolfram

> Auto-generated documentation for [bot.cogs.wolfram](https://github.com/python-discord/bot/blob/master/bot/cogs/wolfram.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Wolfram
  - [Wolfram](#wolfram)
  - [custom_cooldown](#custom_cooldown)
  - [get_pod_pages](#get_pod_pages)
  - [send_embed](#send_embed)
  - [setup](#setup)

## Wolfram

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/wolfram.py#L151)

```python
class Wolfram(bot: Bot)
```

Commands for interacting with the Wolfram|Alpha API.

## custom_cooldown

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/wolfram.py#L55)

```python
def custom_cooldown(ignore: List[int]) -> Callable
```

Implement per-user and per-guild cooldowns for requests to the Wolfram API.

A list of roles may be provided to ignore the per-user cooldown

## get_pod_pages

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/wolfram.py#L97)

```python
def get_pod_pages(
    ctx: Context,
    bot: Bot,
    query: str,
) -> Union[List[Tuple], NoneType]
```

Get the Wolfram API pod pages for the provided query.

## send_embed

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/wolfram.py#L32)

```python
def send_embed(
    ctx: Context,
    message_txt: str,
    colour: int = 13462893,
    footer: str = None,
    img_url: str = None,
    f: File = None,
) -> None
```

Generate & send a response embed with Wolfram as the author.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/wolfram.py#L269)

```python
def setup(bot: Bot) -> None
```

Wolfram cog load.
