import datetime
import re
from enum import Enum
from time import struct_time
from typing import Optional, Union

import arrow
from dateutil.relativedelta import relativedelta

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
Timestamp = Union[
    arrow.Arrow,
    datetime.datetime,
    datetime.date,
    struct_time,
    int,  # POSIX timestamp
    float,  # POSIX timestamp
    str,  # ISO 8601-formatted string
    tuple[int, int, int],  # ISO calendar tuple
]


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
    Returns a string to represent a value and time unit, ensuring that it uses the right plural form of the unit.

    >>> _stringify_time_unit(1, "seconds")
    "1 second"
    >>> _stringify_time_unit(24, "hours")
    "24 hours"
    >>> _stringify_time_unit(0, "minutes")
    "less than a minute"
    """
    if unit == "seconds" and value == 0:
        return "0 seconds"
    elif value == 1:
        return f"{value} {unit[:-1]}"
    elif value == 0:
        return f"less than a {unit[:-1]}"
    else:
        return f"{value} {unit}"


def discord_timestamp(timestamp: Timestamp, format: TimestampFormats = TimestampFormats.DATE_TIME) -> str:
    """
    Format a timestamp as a Discord-flavored Markdown timestamp.

    `timestamp` can be any type supported by the single-arg `arrow.get()`, except for a `tzinfo`.
    """
    timestamp = int(arrow.get(timestamp).timestamp())
    return f"<t:{timestamp}:{format.value}>"


def humanize_delta(delta: relativedelta, precision: str = "seconds", max_units: int = 6) -> str:
    """
    Returns a human-readable version of the relativedelta.

    precision specifies the smallest unit of time to include (e.g. "seconds", "minutes").
    max_units specifies the maximum number of units of time to include (e.g. 1 may include days but not hours).
    """
    if max_units <= 0:
        raise ValueError("max_units must be positive")

    units = (
        ("years", delta.years),
        ("months", delta.months),
        ("days", delta.days),
        ("hours", delta.hours),
        ("minutes", delta.minutes),
        ("seconds", delta.seconds),
    )

    # Add the time units that are >0, but stop at accuracy or max_units.
    time_strings = []
    unit_count = 0
    for unit, value in units:
        if value:
            time_strings.append(_stringify_time_unit(value, unit))
            unit_count += 1

        if unit == precision or unit_count >= max_units:
            break

    # Add the 'and' between the last two units, if necessary
    if len(time_strings) > 1:
        time_strings[-1] = f"{time_strings[-2]} and {time_strings[-1]}"
        del time_strings[-2]

    # If nothing has been found, just make the value 0 precision, e.g. `0 days`.
    if not time_strings:
        humanized = _stringify_time_unit(0, precision)
    else:
        humanized = ", ".join(time_strings)

    return humanized


def parse_duration_string(duration: str) -> Optional[relativedelta]:
    """
    Converts a `duration` string to a relativedelta object.

    The function supports the following symbols for each unit of time:
    - years: `Y`, `y`, `year`, `years`
    - months: `m`, `month`, `months`
    - weeks: `w`, `W`, `week`, `weeks`
    - days: `d`, `D`, `day`, `days`
    - hours: `H`, `h`, `hour`, `hours`
    - minutes: `M`, `minute`, `minutes`
    - seconds: `S`, `s`, `second`, `seconds`
    The units need to be provided in descending order of magnitude.
    If the string does represent a durationdelta object, it will return None.
    """
    match = _DURATION_REGEX.fullmatch(duration)
    if not match:
        return None

    duration_dict = {unit: int(amount) for unit, amount in match.groupdict(default=0).items()}
    delta = relativedelta(**duration_dict)

    return delta


def relativedelta_to_timedelta(delta: relativedelta) -> datetime.timedelta:
    """Converts a relativedelta object to a timedelta object."""
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
    timestamp: Optional[Timestamp],
    other_timestamp: Optional[Timestamp] = None,
    max_units: int = 2,
) -> Optional[str]:
    """
    Return `timestamp` formatted as a discord timestamp with the timestamp duration since `other_timestamp`.

    `timestamp` and `other_timestamp` can be any type supported by the single-arg `arrow.get()`,
    except for a `tzinfo`. Use the current time if `other_timestamp` is falsy or unspecified.

    `max_units` specifies the maximum number of units of time to include in the duration. For
    example, a value of 1 may include days but not hours.

    Return None if `timestamp` is falsy.
    """
    if not timestamp:
        return None

    timestamp = arrow.get(timestamp)
    if not other_timestamp:
        other_timestamp = arrow.utcnow()
    else:
        other_timestamp = arrow.get(other_timestamp)

    formatted_timestamp = discord_timestamp(timestamp)
    delta = abs(relativedelta(timestamp.datetime, other_timestamp.datetime))
    duration = humanize_delta(delta, max_units=max_units)

    return f"{formatted_timestamp} ({duration})"


def until_expiration(expiry: Optional[Timestamp]) -> Optional[str]:
    """
    Get the remaining time until an infraction's expiration as a Discord timestamp.

    `expiry` can be any type supported by the single-arg `arrow.get()`, except for a `tzinfo`.

    Return None if `expiry` is falsy or is in the past.
    """
    if not expiry:
        return None

    expiry = arrow.get(expiry)
    if expiry < arrow.utcnow():
        return None

    return format_relative(expiry)
