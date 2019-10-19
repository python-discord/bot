# OffTopicNames

> Auto-generated documentation for [bot.cogs.off_topic_names](https://github.com/python-discord/bot/blob/master/bot/cogs/off_topic_names.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / OffTopicNames
  - [OffTopicName](#offtopicname)
    - [OffTopicName.convert](#offtopicnameconvert)
  - [OffTopicNames](#offtopicnames)
    - [OffTopicNames().cog_unload](#offtopicnamescog_unload)
    - [OffTopicNames().init_offtopic_updater](#offtopicnamesinit_offtopic_updater)
  - [setup](#setup)
  - [update_names](#update_names)

## OffTopicName

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/off_topic_names.py#L19)

```python
class OffTopicName()
```

A converter that ensures an added off-topic name is valid.

### OffTopicName.convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/off_topic_names.py#L22)

```python
def convert(ctx: Context, argument: str) -> str
```

Attempt to replace any invalid characters with their approximate Unicode equivalent.

## OffTopicNames

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/off_topic_names.py#L71)

```python
class OffTopicNames(bot: Bot)
```

Commands related to managing the off-topic category channel names.

### OffTopicNames().cog_unload

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/off_topic_names.py#L80)

```python
def cog_unload() -> None
```

Cancel any running updater tasks on cog unload.

### OffTopicNames().init_offtopic_updater

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/off_topic_names.py#L85)

```python
def init_offtopic_updater() -> None
```

Start off-topic channel updating event loop if it hasn't already started.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/off_topic_names.py#L190)

```python
def setup(bot: Bot) -> None
```

Off topic names cog load.

## update_names

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/off_topic_names.py#L43)

```python
def update_names(bot: Bot) -> None
```

Background updater task that performs the daily channel name update.
