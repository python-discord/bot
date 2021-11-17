import datetime
import re
from enum import Enum
from typing import Optional, Union

import arrow
import dateutil.parser
from dateutil.relativedelta import relativedelta

RFC1123_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"
DISCORD_TIMESTAMP_REGEX = re.compile(r"<t:(\d+):f>")

_DURATION_REGEX = re.compile(
    r"((?P<years>\d+?) ?(years|year|Y|y) ?)?"
    r"((?P<months>\d+?) ?(months|month|m) ?)?"
    r"((?P<weeks>\d+?) ?(weeks|week|W|w) ?)?"
    r"((?P<days>\d+?) ?(days|day|D|d) ?)?"
    r"((?P<hours>\d+?) ?(hours|hour|H|h) ?)?"
    r"((?P<minutes>\d+?) ?(minutes|minute|M) ?)?"
    r"((?P<seconds>\d+?) ?(seconds|second|S|s))?"
)


ValidTimestamp = Union[
    int, datetime.datetime, datetime.date, datetime.timedelta, relativedelta
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


def discord_timestamp(
    timestamp: ValidTimestamp, format: TimestampFormats = TimestampFormats.DATE_TIME
) -> str:
    """Create and format a Discord flavored markdown timestamp."""
    if format not in TimestampFormats:
        raise ValueError(
            f"Format can only be one of {', '.join(TimestampFormats.args)}, not {format}."
        )

    # Convert each possible timestamp class to an integer.
    if isinstance(timestamp, datetime.datetime):
        timestamp = (timestamp - arrow.get(0)).total_seconds()
    elif isinstance(timestamp, datetime.date):
        timestamp = (timestamp - arrow.get(0)).total_seconds()
    elif isinstance(timestamp, datetime.timedelta):
        timestamp = timestamp.total_seconds()
    elif isinstance(timestamp, relativedelta):
        timestamp = timestamp.seconds

    return f"<t:{int(timestamp)}:{format.value}>"


def humanize_delta(
    delta: relativedelta, precision: str = "seconds", max_units: int = 6
) -> str:
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


def get_time_delta(time_string: str) -> str:
    """Returns the time in human-readable time delta format."""
    date_time = dateutil.parser.isoparse(time_string)
    time_delta = time_since(date_time)

    return time_delta


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

    duration_dict = {
        unit: int(amount) for unit, amount in match.groupdict(default=0).items()
    }
    delta = relativedelta(**duration_dict)

    return delta


def relativedelta_to_timedelta(delta: relativedelta) -> datetime.timedelta:
    """Converts a relativedelta object to a timedelta object."""
    utcnow = arrow.utcnow()
    return utcnow + delta - utcnow


def time_since(past_datetime: datetime.datetime) -> str:
    """Takes a datetime and returns a discord timestamp that describes how long ago that datetime was."""
    return discord_timestamp(past_datetime, TimestampFormats.RELATIVE)


def parse_rfc1123(stamp: str) -> datetime.datetime:
    """Parse RFC1123 time string into datetime."""
    return datetime.datetime.strptime(stamp, RFC1123_FORMAT).replace(
        tzinfo=datetime.timezone.utc
    )


def format_infraction(timestamp: str) -> str:
    """Format an infraction timestamp to a discord timestamp."""
    return discord_timestamp(dateutil.parser.isoparse(timestamp))


def format_infraction_with_duration(
    date_to: Optional[str],
    date_from: Optional[datetime.datetime] = None,
    max_units: int = 2,
    absolute: bool = True,
) -> Optional[str]:
    """
    Return `date_to` formatted as a discord timestamp with the timestamp duration since `date_from`.

    `max_units` specifies the maximum number of units of time to include in the duration. For
    example, a value of 1 may include days but not hours.

    If `absolute` is True, the absolute value of the duration delta is used. This prevents negative
    values in the case that `date_to` is in the past relative to `date_from`.
    """
    if not date_to:
        return None

    date_to_formatted = format_infraction(date_to)

    date_from = date_from or datetime.datetime.now(datetime.timezone.utc)
    date_to = dateutil.parser.isoparse(date_to).replace(microsecond=0)

    delta = relativedelta(date_to, date_from)
    if absolute:
        delta = abs(delta)

    duration = humanize_delta(delta, max_units=max_units)
    duration_formatted = f" ({duration})" if duration else ""

    return f"{date_to_formatted}{duration_formatted}"


def until_expiration(expiry: Optional[str]) -> Optional[str]:
    """
    Get the remaining time until infraction's expiration, in a discord timestamp.

    Returns a human-readable version of the remaining duration between arrow.utcnow() and an expiry.
    Similar to time_since, except that this function doesn't error on a null input
    and return null if the expiry is in the paste
    """
    if not expiry:
        return None

    now = arrow.utcnow()
    since = dateutil.parser.isoparse(expiry).replace(microsecond=0)

    if since < now:
        return None

    return discord_timestamp(since, TimestampFormats.RELATIVE)
