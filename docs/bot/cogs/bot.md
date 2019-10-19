# Bot

> Auto-generated documentation for [bot.cogs.bot](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Bot
  - [Bot](#bot)
    - [Bot().codeblock_stripping](#botcodeblock_stripping)
    - [Bot().fix_indentation](#botfix_indentation)
    - [Bot().has_bad_ticks](#bothas_bad_ticks)
    - [Bot().on_message](#boton_message)
    - [Bot().on_raw_message_edit](#boton_raw_message_edit)
    - [Bot().repl_stripping](#botrepl_stripping)
  - [setup](#setup)

## Bot

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py#L19)

```python
class Bot(bot: Bot)
```

Bot information commands.

### Bot().codeblock_stripping

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py#L85)

```python
def codeblock_stripping(
    msg: str,
    bad_ticks: bool,
) -> Union[Tuple[Tuple[str, ...], str], NoneType]
```

Strip msg in order to find Python code.

Tries to strip out Python code out of msg and returns the stripped block or
None if the block is a valid Python codeblock.

### Bot().fix_indentation

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py#L154)

```python
def fix_indentation(msg: str) -> str
```

Attempts to fix badly indented code.

### Bot().has_bad_ticks

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py#L213)

```python
def has_bad_ticks(msg: Message) -> bool
```

Check to see if msg contains ticks that aren't '`'.

### Bot().on_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py#L223)

```python
def on_message(msg: Message) -> None
```

Detect poorly formatted Python code in new messages.

If poorly formatted code is detected, send the user a helpful message explaining how to do
properly formatted Python syntax highlighting codeblocks.

### Bot().on_raw_message_edit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py#L348)

```python
def on_raw_message_edit(payload: RawMessageUpdateEvent) -> None
```

Check to see if an edited message (previously called out) still contains poorly formatted code.

### Bot().repl_stripping

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py#L193)

```python
def repl_stripping(msg: str) -> Tuple[str, bool]
```

Strip msg in order to extract Python code out of REPL output.

Tries to strip out REPL Python code out of msg and returns the stripped msg.

Returns True for the boolean if REPL code was found in the input msg.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/bot.py#L376)

```python
def setup(bot: Bot) -> None
```

Bot cog load.

#### See also

- [Bot](#bot)
