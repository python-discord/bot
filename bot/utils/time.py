import asyncio
import datetime
import re
from typing import Optional

import dateutil.parser
from dateutil.relativedelta import relativedelta

RFC1123_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"
INFRACTION_FORMAT = "%Y-%m-%d %H:%M"

_DURATION_REGEX = re.compile(
    r"((?P<years>\d+?) ?(years|year|Y|y) ?)?"
    r"((?P<months>\d+?) ?(months|month|m) ?)?"
    r"((?P<weeks>\d+?) ?(weeks|week|W|w) ?)?"
    r"((?P<days>\d+?) ?(days|day|D|d) ?)?"
    r"((?P<hours>\d+?) ?(hours|hour|H|h) ?)?"
    r"((?P<minutes>\d+?) ?(minutes|minute|M) ?)?"
    r"((?P<seconds>\d+?) ?(seconds|second|S|s))?"
)


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
    utcnow = datetime.datetime.utcnow()
    return utcnow + delta - utcnow


def time_since(past_datetime: datetime.datetime, precision: str = "seconds", max_units: int = 6) -> str:
    """
    Takes a datetime and returns a human-readable string that describes how long ago that datetime was.

    precision specifies the smallest unit of time to include (e.g. "seconds", "minutes").
    max_units specifies the maximum number of units of time to include (e.g. 1 may include days but not hours).
    """
    now = datetime.datetime.utcnow()
    delta = abs(relativedelta(now, past_datetime))

    humanized = humanize_delta(delta, precision, max_units)

    return f"{humanized} ago"


def parse_rfc1123(stamp: str) -> datetime.datetime:
    """Parse RFC1123 time string into datetime."""
    return datetime.datetime.strptime(stamp, RFC1123_FORMAT).replace(tzinfo=datetime.timezone.utc)


# Hey, this could actually be used in the off_topic_names and reddit cogs :)
async def wait_until(time: datetime.datetime, start: Optional[datetime.datetime] = None) -> None:
    """
    Wait until a given time.

    :param time: A datetime.datetime object to wait until.
    :param start: The start from which to calculate the waiting duration. Defaults to UTC time.
    """
    delay = time - (start or datetime.datetime.utcnow())
    delay_seconds = delay.total_seconds()

    # Incorporate a small delay so we don't rapid-fire the event due to time precision errors
    if delay_seconds > 1.0:
        await asyncio.sleep(delay_seconds)


def format_infraction(timestamp: str) -> str:
    """Format an infraction timestamp to a more readable ISO 8601 format."""
    return dateutil.parser.isoparse(timestamp).strftime(INFRACTION_FORMAT)


def format_infraction_with_duration(
    date_to: Optional[str],
    date_from: Optional[datetime.datetime] = None,
    max_units: int = 2,
    absolute: bool = True
) -> Optional[str]:
    """
    Return `date_to` formatted as a readable ISO-8601 with the humanized duration since `date_from`.

    `date_from` must be an ISO-8601 formatted timestamp. The duration is calculated as from
    `date_from` until `date_to` with a precision of seconds. If `date_from` is unspecified, the
    current time is used.

    `max_units` specifies the maximum number of units of time to include in the duration. For
    example, a value of 1 may include days but not hours.

    If `absolute` is True, the absolute value of the duration delta is used. This prevents negative
    values in the case that `date_to` is in the past relative to `date_from`.
    """
    if not date_to:
        return None

    date_to_formatted = format_infraction(date_to)

    date_from = date_from or datetime.datetime.utcnow()
    date_to = dateutil.parser.isoparse(date_to).replace(tzinfo=None, microsecond=0)

    delta = relativedelta(date_to, date_from)
    if absolute:
        delta = abs(delta)

    duration = humanize_delta(delta, max_units=max_units)
    duration_formatted = f" ({duration})" if duration else ""

    return f"{date_to_formatted}{duration_formatted}"


def until_expiration(
    expiry: Optional[str],
    now: Optional[datetime.datetime] = None,
    max_units: int = 2
) -> Optional[str]:
    """
    Get the remaining time until infraction's expiration, in a human-readable version of the relativedelta.

    Returns a human-readable version of the remaining duration between datetime.utcnow() and an expiry.
    Unlike `humanize_delta`, this function will force the `precision` to be `seconds` by not passing it.
    `max_units` specifies the maximum number of units of time to include (e.g. 1 may include days but not hours).
    By default, max_units is 2.
    """
    if not expiry:
        return None

    now = now or datetime.datetime.utcnow()
    since = dateutil.parser.isoparse(expiry).replace(tzinfo=None, microsecond=0)

    if since < now:
        return None

    return humanize_delta(relativedelta(since, now), max_units=max_units)
