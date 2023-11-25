from __future__ import annotations

import datetime
import re
from copy import copy
from enum import Enum
from time import struct_time
from typing import Literal, TYPE_CHECKING, overload

import arrow
from dateutil.relativedelta import relativedelta

if TYPE_CHECKING:
    from bot.converters import DurationOrExpiry

_DURATION_REGEX = re.compile(
    r"((?P<years>\d+?) ?(years|year|Y|y) ?)?"
    r"((?P<months>\d+?) ?(months|month|m) ?)?"
    r"((?P<weeks>\d+?) ?(weeks|week|W|w) ?)?"
    r"((?P<days>\d+?) ?(days|day|D|d) ?)?"
    r"((?P<hours>\d+?) ?(hours|hour|H|h) ?)?"
    r"((?P<minutes>\d+?) ?(minutes|minute|M) ?)?"
    r"((?P<seconds>\d+?) ?(seconds|second|S|s))?"
)

# All supported types for the single-argument overload of arrow.get(). tzinfo is excluded because
# it's too implicit of a way for the caller to specify that they want the current time.
Timestamp = (
    arrow.Arrow
    | datetime.datetime
    | datetime.date
    | struct_time
    | int  # POSIX timestamp
    | float  # POSIX timestamp
    | str  # ISO 8601-formatted string
    | tuple[int, int, int]  # ISO calendar tuple
)
_Precision = Literal["years", "months", "days", "hours", "minutes", "seconds"]


class TimestampFormats(Enum):
    """
    Represents the different formats possible for Discord timestamps.

    Examples are given in epoch time.
    """

    DATE_TIME = "f"  # January 1, 1970 1:00 AM
    DAY_TIME = "F"  # Thursday, January 1, 1970 1:00 AM
    DATE_SHORT = "d"  # 01/01/1970
    DATE = "D"  # January 1, 1970
    TIME = "t"  # 1:00 AM
    TIME_SECONDS = "T"  # 1:00:00 AM
    RELATIVE = "R"  # 52 years ago


def _stringify_time_unit(value: int, unit: str) -> str:
    """
    Return a string to represent a value and time unit, ensuring the unit's correct plural form is used.

    >>> _stringify_time_unit(1, "seconds")
    "1 second"
    >>> _stringify_time_unit(24, "hours")
    "24 hours"
    >>> _stringify_time_unit(0, "minutes")
    "less than a minute"
    """
    if unit == "seconds" and value == 0:
        return "0 seconds"
    if value == 1:
        return f"{value} {unit[:-1]}"
    if value == 0:
        return f"less than a {unit[:-1]}"
    return f"{value} {unit}"


def discord_timestamp(timestamp: Timestamp, format: TimestampFormats = TimestampFormats.DATE_TIME) -> str:
    """
    Format a timestamp as a Discord-flavored Markdown timestamp.

    `timestamp` can be any type supported by the single-arg `arrow.get()`, except for a `tzinfo`.
    """
    timestamp = int(arrow.get(timestamp).timestamp())
    return f"<t:{timestamp}:{format.value}>"


# region humanize_delta overloads
@overload
def humanize_delta(
    arg1: relativedelta | Timestamp,
    /,
    *,
    precision: _Precision = "seconds",
    max_units: int = 6,
    absolute: bool = True,
) -> str:
    ...


@overload
def humanize_delta(
    end: Timestamp,
    start: Timestamp,
    /,
    *,
    precision: _Precision = "seconds",
    max_units: int = 6,
    absolute: bool = True,
) -> str:
    ...


@overload
def humanize_delta(
    *,
    years: int = 0,
    months: int = 0,
    weeks: float = 0,
    days: float = 0,
    hours: float = 0,
    minutes: float = 0,
    seconds: float = 0,
    precision: _Precision = "seconds",
    max_units: int = 6,
    absolute: bool = True,
) -> str:
    ...
# endregion


def humanize_delta(
    *args,
    precision: _Precision = "seconds",
    max_units: int = 6,
    absolute: bool = True,
    **kwargs,
) -> str:
    """
    Return a human-readable version of a time duration.

    `precision` is the smallest unit of time to include (e.g. "seconds", "minutes").

    `max_units` is the maximum number of units of time to include.
    Count units from largest to smallest (e.g. count days before months).

    Use the absolute value of the duration if `absolute` is True.

    Usage:

    Keyword arguments specifying values for time units, to construct a `relativedelta` and humanize
    the duration represented by it:

    >>> humanize_delta(days=2, hours=16, seconds=23)
    '2 days, 16 hours and 23 seconds'

    **One** `relativedelta` object, to humanize the duration represented by it:

    >>> humanize_delta(relativedelta(years=12, months=6))
    '12 years and 6 months'

    Note that `leapdays` and absolute info (singular names) will be ignored during humanization.

    **One** timestamp of a type supported by the single-arg `arrow.get()`, except for `tzinfo`,
    to humanize the duration between it and the current time:

    >>> humanize_delta('2021-08-06T12:43:01Z', absolute=True)  # now = 2021-08-06T12:33:33Z
    '9 minutes and 28 seconds'

    >>> humanize_delta('2021-08-06T12:43:01Z', absolute=False)  # now = 2021-08-06T12:33:33Z
    '-9 minutes and -28 seconds'

    **Two** timestamps, each of a type supported by the single-arg `arrow.get()`, except for
    `tzinfo`, to humanize the duration between them:

    >>> humanize_delta(datetime.datetime(2020, 1, 1), '2021-01-01T12:00:00Z', absolute=False)
    '1 year and 12 hours'

    >>> humanize_delta('2021-01-01T12:00:00Z', datetime.datetime(2020, 1, 1), absolute=False)
    '-1 years and -12 hours'

    Note that order of the arguments can result in a different output even if `absolute` is True:

    >>> x = datetime.datetime(3000, 11, 1)
    >>> y = datetime.datetime(3000, 9, 2)
    >>> humanize_delta(y, x, absolute=True), humanize_delta(x, y, absolute=True)
    ('1 month and 30 days', '1 month and 29 days')

    This is due to the nature of `relativedelta`; it does not represent a fixed period of time.
    Instead, it's relative to the `datetime` to which it's added to get the other `datetime`.
    In the example, the difference arises because all months don't have the same number of days.
    """
    if args and kwargs:
        raise ValueError("Unsupported combination of positional and keyword arguments.")

    if len(args) == 0:
        delta = relativedelta(**kwargs)
    elif len(args) == 1 and isinstance(args[0], relativedelta):
        delta = args[0]
    elif len(args) <= 2:
        end = arrow.get(args[0])
        start = arrow.get(args[1]) if len(args) == 2 else arrow.utcnow()
        delta = round_delta(relativedelta(end.datetime, start.datetime))

        if absolute:
            delta = abs(delta)
    else:
        raise ValueError(f"Received {len(args)} positional arguments, but expected 1 or 2.")

    if max_units <= 0:
        raise ValueError("max_units must be positive.")

    units = (
        ("years", delta.years),
        ("months", delta.months),
        ("days", delta.days),
        ("hours", delta.hours),
        ("minutes", delta.minutes),
        ("seconds", delta.seconds),
    )

    # Add the time units that are >0, but stop at precision or max_units.
    time_strings = []
    unit_count = 0
    for unit, value in units:
        if value:
            time_strings.append(_stringify_time_unit(value, unit))
            unit_count += 1

        if unit == precision or unit_count >= max_units:
            break

    # Add the 'and' between the last two units, if necessary.
    if len(time_strings) > 1:
        time_strings[-1] = f"{time_strings[-2]} and {time_strings[-1]}"
        del time_strings[-2]

    # If nothing has been found, just make the value 0 precision, e.g. `0 days`.
    if not time_strings:
        humanized = _stringify_time_unit(0, precision)
    else:
        humanized = ", ".join(time_strings)

    return humanized


def parse_duration_string(duration: str) -> relativedelta | None:
    """
    Convert a `duration` string to a relativedelta object.

    The following symbols are supported for each unit of time:

    - years: `Y`, `y`, `year`, `years`
    - months: `m`, `month`, `months`
    - weeks: `w`, `W`, `week`, `weeks`
    - days: `d`, `D`, `day`, `days`
    - hours: `H`, `h`, `hour`, `hours`
    - minutes: `M`, `minute`, `minutes`
    - seconds: `S`, `s`, `second`, `seconds`

    The units need to be provided in descending order of magnitude.
    Return None if the `duration` string cannot be parsed according to the symbols above.
    """
    match = _DURATION_REGEX.fullmatch(duration)
    if not match:
        return None

    duration_dict = {unit: int(amount) for unit, amount in match.groupdict(default=0).items()}
    delta = relativedelta(**duration_dict)

    return delta


def relativedelta_to_timedelta(delta: relativedelta) -> datetime.timedelta:
    """Convert a relativedelta object to a timedelta object."""
    utcnow = arrow.utcnow()
    return utcnow + delta - utcnow


def format_relative(timestamp: Timestamp) -> str:
    """
    Format `timestamp` as a relative Discord timestamp.

    A relative timestamp describes how much time has elapsed since `timestamp` or how much time
    remains until `timestamp` is reached.

    `timestamp` can be any type supported by the single-arg `arrow.get()`, except for a `tzinfo`.
    """
    return discord_timestamp(timestamp, TimestampFormats.RELATIVE)


def format_with_duration(
    timestamp: Timestamp | None,
    other_timestamp: Timestamp | None = None,
    max_units: int = 2,
) -> str | None:
    """
    Return `timestamp` formatted as a discord timestamp with the timestamp duration since `other_timestamp`.

    `timestamp` and `other_timestamp` can be any type supported by the single-arg `arrow.get()`,
    except for a `tzinfo`. Use the current time if `other_timestamp` is None or unspecified.

    `max_units` is forwarded to `time.humanize_delta`. See its documentation for more information.

    Return None if `timestamp` is None.
    """
    if timestamp is None:
        return None

    if other_timestamp is None:
        other_timestamp = arrow.utcnow()

    formatted_timestamp = discord_timestamp(timestamp)
    duration = humanize_delta(timestamp, other_timestamp, max_units=max_units)

    return f"{formatted_timestamp} ({duration})"


def until_expiration(expiry: Timestamp | None) -> str:
    """
    Get the remaining time until an infraction's expiration as a Discord timestamp.

    `expiry` can be any type supported by the single-arg `arrow.get()`, except for a `tzinfo`.

    Return "Permanent" if `expiry` is None. Return "Expired" if `expiry` is in the past.
    """
    if expiry is None:
        return "Permanent"

    expiry = arrow.get(expiry)
    if expiry < arrow.utcnow():
        return "Expired"

    return format_relative(expiry)


def unpack_duration(
        duration_or_expiry: DurationOrExpiry,
        origin: datetime.datetime | arrow.Arrow | None = None
) -> tuple[datetime.datetime, datetime.datetime]:
    """
    Unpacks a DurationOrExpiry into a tuple of (origin, expiry).

    The `origin` defaults to the current UTC time at function call.
    """
    if origin is None:
        origin = datetime.datetime.now(tz=datetime.UTC)

    if isinstance(origin, arrow.Arrow):
        origin = origin.datetime

    if isinstance(duration_or_expiry, relativedelta):
        return origin, origin + duration_or_expiry
    return origin, duration_or_expiry


def round_delta(delta: relativedelta) -> relativedelta:
    """
    Rounds `delta` to the nearest second.

    Returns a copy with microsecond values of 0.
    """
    delta = copy(delta)
    if delta.microseconds >= 500000:
        delta += relativedelta(seconds=1)
    delta.microseconds = 0
    return delta
