# Scheduling

> Auto-generated documentation for [bot.utils.scheduling](https://github.com/python-discord/bot/blob/master/bot/utils/scheduling.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Utils](index.md#utils) / Scheduling
  - [Scheduler](#scheduler)
    - [Scheduler().cancel_task](#schedulercancel_task)
    - [Scheduler().schedule_task](#schedulerschedule_task)
  - [_silent_exception](#_silent_exception)
  - [create_task](#create_task)

## Scheduler

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/scheduling.py#L12)

```python
class Scheduler()
```

Task scheduler.

### Scheduler().cancel_task

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/scheduling.py#L45)

```python
def cancel_task(task_id: str) -> None
```

Un-schedules a task.

### Scheduler().schedule_task

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/scheduling.py#L32)

```python
def schedule_task(
    loop: AbstractEventLoop,
    task_id: str,
    task_data: dict,
) -> None
```

Schedules a task.

`task_data` is passed to `Scheduler._scheduled_expiration`

## _silent_exception

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/scheduling.py#L67)

```python
def _silent_exception(future: Future) -> None
```

Suppress future's exception.

## create_task

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/scheduling.py#L58)

```python
def create_task(
    loop: AbstractEventLoop,
    coro_or_future: Union[Coroutine, _asyncio.Future],
) -> Task
```

Creates an asyncio.Task object from a coroutine or future object.
