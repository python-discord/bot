# Snekbox

> Auto-generated documentation for [bot.cogs.snekbox](https://github.com/python-discord/bot/blob/master/bot/cogs/snekbox.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Snekbox
  - [Snekbox](#snekbox)
    - [Snekbox().format_output](#snekboxformat_output)
    - [Snekbox.get_results_message](#snekboxget_results_message)
    - [Snekbox().post_eval](#snekboxpost_eval)
    - [Snekbox.prepare_input](#snekboxprepare_input)
    - [Snekbox().upload_output](#snekboxupload_output)
  - [setup](#setup)

## Snekbox

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/snekbox.py#L39)

```python
class Snekbox(bot: Bot)
```

Safe evaluation of Python code using Snekbox.

### Snekbox().format_output

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/snekbox.py#L118)

```python
def format_output(output: str) -> Tuple[str, Union[str, NoneType]]
```

Format the output and return a tuple of the formatted output and a URL to the full output.

Prepend each line with a line number. Truncate if there are over 10 lines or 1000 characters
and upload the full output to a paste service.

### Snekbox.get_results_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/snekbox.py#L93)

```python
def get_results_message(results: dict) -> Tuple[str, str]
```

Return a user-friendly message and error corresponding to the process's return code.

### Snekbox().post_eval

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/snekbox.py#L46)

```python
def post_eval(code: str) -> dict
```

Send a POST request to the Snekbox API to evaluate code and return the results.

### Snekbox.prepare_input

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/snekbox.py#L72)

```python
def prepare_input(code: str) -> str
```

Extract code from the Markdown, format it, and insert it into the code template.

### Snekbox().upload_output

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/snekbox.py#L53)

```python
def upload_output(output: str) -> Union[str, NoneType]
```

Upload the eval output to a paste service and return a URL to it if successful.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/snekbox.py#L218)

```python
def setup(bot: Bot) -> None
```

Snekbox cog load.
