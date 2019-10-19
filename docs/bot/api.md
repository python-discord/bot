# Api

> Auto-generated documentation for [bot.api](https://github.com/python-discord/bot/blob/master/bot/api.py) module.

- [Index](../README.md#modules) / [Bot](index.md#bot) / Api
  - [APIClient](#apiclient)
    - [APIClient().delete](#apiclientdelete)
    - [APIClient().get](#apiclientget)
    - [APIClient().maybe_raise_for_status](#apiclientmaybe_raise_for_status)
    - [APIClient().patch](#apiclientpatch)
    - [APIClient().post](#apiclientpost)
    - [APIClient().put](#apiclientput)
  - [APILoggingHandler](#apilogginghandler)
    - [APILoggingHandler().emit](#apilogginghandleremit)
    - [APILoggingHandler().schedule_queued_tasks](#apilogginghandlerschedule_queued_tasks)
    - [APILoggingHandler().ship_off](#apilogginghandlership_off)
  - [ResponseCodeError](#responsecodeerror)
  - [loop_is_running](#loop_is_running)

## APIClient

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L32)

```python
class APIClient(kwargs)
```

Django Site API wrapper.

### APIClient().delete

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L85)

```python
def delete(endpoint: str, args, kwargs) -> Union[dict, NoneType]
```

Site API DELETE.

### APIClient().get

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L61)

```python
def get(endpoint: str, args, kwargs) -> dict
```

Site API GET.

### APIClient().maybe_raise_for_status

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L51)

```python
def maybe_raise_for_status(
    response: ClientResponse,
    should_raise: bool,
) -> None
```

Raise ResponseCodeError for non-OK response if an exception should be raised.

### APIClient().patch

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L67)

```python
def patch(endpoint: str, args, kwargs) -> dict
```

Site API PATCH.

### APIClient().post

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L73)

```python
def post(endpoint: str, args, kwargs) -> dict
```

Site API POST.

### APIClient().put

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L79)

```python
def put(endpoint: str, args, kwargs) -> dict
```

Site API PUT.

## APILoggingHandler

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L109)

```python
class APILoggingHandler(client: APIClient)
```

Site API logging handler.

#### See also

- [APIClient](#apiclient)

### APILoggingHandler().emit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L137)

```python
def emit(record: LogRecord) -> None
```

Determine if a log record should be shipped to the logging API.

If the asyncio event loop is not yet running, log records will instead be put in a queue
which will be consumed once the event loop is running.

The following two conditions are set:
    1. Do not log anything below DEBUG (only applies to the monkeypatched `TRACE` level)
    2. Ignore log records originating from this logging handler itself to prevent infinite recursion

### APILoggingHandler().schedule_queued_tasks

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L168)

```python
def schedule_queued_tasks() -> None
```

Consume the queue and schedule the logging of each queued record.

### APILoggingHandler().ship_off

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L120)

```python
def ship_off(payload: dict) -> None
```

Ship log payload to the logging API.

## ResponseCodeError

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L13)

```python
class ResponseCodeError(
    response: ClientResponse,
    response_json: Union[dict, NoneType] = None,
    response_text: str = '',
)
```

Raised when a non-OK HTTP response is received.

## loop_is_running

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/api.py#L95)

```python
def loop_is_running() -> bool
```

Determine if there is a running asyncio event loop.

This helps enable "call this when event loop is running" logic (see: Twisted's `callWhenRunning`),
which is currently not provided by asyncio.
