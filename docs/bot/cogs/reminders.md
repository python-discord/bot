# Reminders

> Auto-generated documentation for [bot.cogs.reminders](https://github.com/python-discord/bot/blob/master/bot/cogs/reminders.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Reminders
  - [Reminders](#reminders)
    - [Reminders().description](#remindersdescription)
    - [Reminders().qualified_name](#remindersqualified_name)
    - [Reminders().reschedule_reminders](#remindersreschedule_reminders)
    - [Reminders().send_reminder](#reminderssend_reminder)
  - [setup](#setup)

## Reminders

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reminders.py#L26)

```python
class Reminders(bot: Bot)
```

Provide in-channel reminder functionality.

### Reminders().description

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reminders.py#L26)

```python
#property getter
def description()
```

class `str`: Returns the cog's description, typically the cleaned docstring.

### Reminders().qualified_name

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reminders.py#L26)

```python
#property getter
def qualified_name()
```

class `str`: Returns the cog's specified name, not the class name.

### Reminders().reschedule_reminders

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reminders.py#L35)

```python
def reschedule_reminders() -> None
```

Get all current reminders from the API and reschedule them.

### Reminders().send_reminder

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reminders.py#L95)

```python
def send_reminder(reminder: dict, late: relativedelta = None) -> None
```

Send the reminder.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reminders.py#L285)

```python
def setup(bot: Bot) -> None
```

Reminders cog load.
