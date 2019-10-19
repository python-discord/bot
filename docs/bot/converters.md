# Converters

> Auto-generated documentation for [bot.converters](https://github.com/python-discord/bot/blob/master/bot/converters.py) module.

- [Index](../README.md#modules) / [Bot](index.md#bot) / Converters
  - [Duration](#duration)
    - [Duration().convert](#durationconvert)
  - [ISODateTime](#isodatetime)
    - [ISODateTime().convert](#isodatetimeconvert)
  - [InfractionSearchQuery](#infractionsearchquery)
    - [InfractionSearchQuery.convert](#infractionsearchqueryconvert)
  - [Subreddit](#subreddit)
    - [Subreddit.convert](#subredditconvert)
  - [TagContentConverter](#tagcontentconverter)
    - [TagContentConverter.convert](#tagcontentconverterconvert)
  - [TagNameConverter](#tagnameconverter)
    - [TagNameConverter.convert](#tagnameconverterconvert)
  - [ValidPythonIdentifier](#validpythonidentifier)
    - [ValidPythonIdentifier.convert](#validpythonidentifierconvert)
  - [ValidURL](#validurl)
    - [ValidURL.convert](#validurlconvert)

## Duration

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L183)

```python
class Duration()
```

Convert duration strings into UTC datetime.datetime objects.

### Duration().convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L196)

```python
def convert(ctx: Context, duration: str) -> datetime
```

Converts a `duration` string to a datetime object that's `duration` in the future.

The converter supports the following symbols for each unit of time:
- years: `Y`, `y`, `year`, `years`
- months: `m`, `month`, `months`
- weeks: `w`, `W`, `week`, `weeks`
- days: `d`, `D`, `day`, `days`
- hours: `H`, `h`, `hour`, `hours`
- minutes: `M`, `minute`, `minutes`
- seconds: `S`, `s`, `second`, `seconds`

The units need to be provided in descending order of magnitude.

## ISODateTime

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L222)

```python
class ISODateTime()
```

Converts an ISO-8601 datetime string into a datetime.datetime.

### ISODateTime().convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L225)

```python
def convert(ctx: Context, datetime_string: str) -> datetime
```

Converts a ISO-8601 `datetime_string` into a `datetime.datetime` object.

The converter is flexible in the formats it accepts, as it uses the `isoparse` method of
`dateutil.parser`. In general, it accepts datetime strings that start with a date,
optionally followed by a time. Specifying a timezone offset in the datetime string is
supported, but the `datetime` object will be converted to UTC and will be returned without
`tzinfo` as a timezone-unaware `datetime` object.

See: https://dateutil.readthedocs.io/en/stable/parser.html#dateutil.parser.isoparse

Formats that are guaranteed to be valid by our tests are:

- `YYYY-mm-ddTHH:MM:SSZ` | `YYYY-mm-dd HH:MM:SSZ`
- `YYYY-mm-ddTHH:MM:SS±HH:MM` | `YYYY-mm-dd HH:MM:SS±HH:MM`
- `YYYY-mm-ddTHH:MM:SS±HHMM` | `YYYY-mm-dd HH:MM:SS±HHMM`
- `YYYY-mm-ddTHH:MM:SS±HH` | `YYYY-mm-dd HH:MM:SS±HH`
- `YYYY-mm-ddTHH:MM:SS` | `YYYY-mm-dd HH:MM:SS`
- `YYYY-mm-ddTHH:MM` | `YYYY-mm-dd HH:MM`
- `YYYY-mm-dd`
- `YYYY-mm`
- `YYYY`

Note: ISO-8601 specifies a `T` as the separator between the date and the time part of the
datetime string. The converter accepts both a `T` and a single space character.

## InfractionSearchQuery

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L69)

```python
class InfractionSearchQuery()
```

A converter that checks if the argument is a Discord user, and if not, falls back to a string.

### InfractionSearchQuery.convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L72)

```python
def convert(ctx: Context, arg: str) -> Union[discord.member.Member, str]
```

Check if the argument is a Discord user, and if not, falls back to a string.

## Subreddit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L82)

```python
class Subreddit()
```

Forces a string to begin with "r/" and checks if it's a valid subreddit.

### Subreddit.convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L85)

```python
def convert(ctx: Context, sub: str) -> str
```

Force sub to begin with "r/" and check if it's a valid subreddit.

If sub is a valid subreddit, return it prepended with "r/"

## TagContentConverter

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L162)

```python
class TagContentConverter()
```

Ensure proposed tag content is not empty and contains at least one non-whitespace character.

### TagContentConverter.convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L165)

```python
def convert(ctx: Context, tag_content: str) -> str
```

Ensure tag_content is non-empty and contains at least one non-whitespace character.

If tag_content is valid, return the stripped version.

## TagNameConverter

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L111)

```python
class TagNameConverter()
```

Ensure that a proposed tag name is valid.

Valid tag names meet the following conditions:
    * All ASCII characters
    * Has at least one non-whitespace character
    * Not solely numeric
    * Shorter than 127 characters

### TagNameConverter.convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L122)

```python
def convert(ctx: Context, tag_name: str) -> str
```

Lowercase & strip whitespace from proposed tag_name & ensure it's valid.

## ValidPythonIdentifier

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L18)

```python
class ValidPythonIdentifier()
```

A converter that checks whether the given string is a valid Python identifier.

This is used to have package names that correspond to how you would use the package in your
code, e.g. `import package`.

Raises `BadArgument` if the argument is not a valid Python identifier, and simply passes through
the given argument otherwise.

### ValidPythonIdentifier.convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L29)

```python
def convert(ctx: Context, argument: str) -> str
```

Checks whether the given string is a valid Python identifier.

## ValidURL

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L37)

```python
class ValidURL()
```

Represents a valid webpage URL.

This converter checks whether the given URL can be reached and requesting it returns a status
code of 200. If not, `BadArgument` is raised.

Otherwise, it simply passes through the given URL.

### ValidURL.convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/converters.py#L47)

```python
def convert(ctx: Context, url: str) -> str
```

This converter checks whether the given URL can be reached with a status code of 200.
