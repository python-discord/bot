# Utils

> Auto-generated documentation for [bot.utils](https://github.com/python-discord/bot/blob/master/bot/utils/__init__.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / Utils
  - [CaseInsensitiveDict](#caseinsensitivedict)
    - [CaseInsensitiveDict().get](#caseinsensitivedictget)
    - [CaseInsensitiveDict().pop](#caseinsensitivedictpop)
    - [CaseInsensitiveDict().setdefault](#caseinsensitivedictsetdefault)
    - [CaseInsensitiveDict().update](#caseinsensitivedictupdate)
  - [CogABCMeta](#cogabcmeta)
  - [chunks](#chunks)
  - Modules
    - [Checks](checks.md#checks)
    - [Messages](messages.md#messages)
    - [Scheduling](scheduling.md#scheduling)
    - [Time](time.md#time)

## CaseInsensitiveDict

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/__init__.py#L13)

```python
class CaseInsensitiveDict()
```

We found this class on StackOverflow. Thanks to m000 for writing it!

https://stackoverflow.com/a/32888599/4022104

### CaseInsensitiveDict().get

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/__init__.py#L49)

```python
def get(key: Hashable, args, kwargs) -> Any
```

Case insensitive get.

### CaseInsensitiveDict().pop

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/__init__.py#L45)

```python
def pop(key: Hashable, args, kwargs) -> Any
```

Case insensitive pop.

### CaseInsensitiveDict().setdefault

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/__init__.py#L53)

```python
def setdefault(key: Hashable, args, kwargs) -> Any
```

Case insensitive setdefault.

### CaseInsensitiveDict().update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/__init__.py#L57)

```python
def update(E: Any, F=None) -> None
```

Case insensitive update.

## CogABCMeta

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/__init__.py#L7)

```python
class CogABCMeta()
```

Metaclass for ABCs meant to be implemented as Cogs.

## chunks

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/__init__.py#L69)

```python
def chunks(iterable: Iterable, size: int) -> Generator[Any, NoneType, NoneType]
```

Generator that allows you to iterate over any indexable collection in `size`-length chunks.

Found: https://stackoverflow.com/a/312464/4022104
