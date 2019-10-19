# Interpreter

> Auto-generated documentation for [bot.interpreter](https://github.com/python-discord/bot/blob/master/bot/interpreter.py) module.

- [Index](../README.md#modules) / [Bot](index.md#bot) / Interpreter
  - [Interpreter](#interpreter)
    - [Interpreter().run](#interpreterrun)

## Interpreter

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/interpreter.py#L13)

```python
class Interpreter(bot: Bot)
```

Subclass InteractiveInterpreter to specify custom run functionality.

Helper class for internal eval.

### Interpreter().run

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/interpreter.py#L26)

```python
def run(code: str, ctx: Context, io: StringIO, args, kwargs) -> Any
```

Execute the provided source code as the bot & return the output.
