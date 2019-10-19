# Time

> Auto-generated documentation for [bot.utils.time](https://github.com/python-discord/bot/blob/master/bot/utils/time.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Utils](index.md#utils) / Time
  - [_stringify_time_unit](#_stringify_time_unit)
  - [format_infraction](#format_infraction)
  - [humanize_delta](#humanize_delta)
  - [parse_rfc1123](#parse_rfc1123)
  - [time_since](#time_since)
  - [wait_until](#wait_until)

## _stringify_time_unit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/time.py#L12)

```python
def _stringify_time_unit(value: int, unit: str) -> str
```

Returns a string to represent a value and time unit, ensuring that it uses the right plural form of the unit.

```python
>>> _stringify_time_unit(1, "seconds")
"1 second"
>>> _stringify_time_unit(24, "hours")
"24 hours"
>>> _stringify_time_unit(0, "minutes")
"less than a minute"
```

## format_infraction

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/time.py#L111)

```python
def format_infraction(timestamp: str) -> str
```

Format an infraction timestamp to a more readable ISO 8601 format.

## humanize_delta

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/time.py#L31)

```python
def humanize_delta(
    delta: relativedelta,
    precision: str = 'seconds',
    max_units: int = 6,
) -> str
```

Returns a human-readable version of the relativedelta.

precision specifies the smallest unit of time to include (e.g. "seconds", "minutes").
max_units specifies the maximum number of units of time to include (e.g. 1 may include days but not hours).

## parse_rfc1123

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/time.py#L90)

```python
def parse_rfc1123(stamp: str) -> datetime
```

Parse RFC1123 time string into datetime.

## time_since

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/time.py#L75)

```python
def time_since(
    past_datetime: datetime,
    precision: str = 'seconds',
    max_units: int = 6,
) -> str
```

Takes a datetime and returns a human-readable string that describes how long ago that datetime was.

precision specifies the smallest unit of time to include (e.g. "seconds", "minutes").
max_units specifies the maximum number of units of time to include (e.g. 1 may include days but not hours).

## wait_until

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/time.py#L96)

```python
def wait_until(
    time: datetime,
    start: Union[datetime.datetime, NoneType] = None,
) -> None
```

Wait until a given time.

#### Arguments

- `time` - A datetime.datetime object to wait until.
- `start` - The start from which to calculate the waiting duration. Defaults to UTC time.
