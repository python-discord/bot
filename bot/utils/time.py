import asyncio
import datetime
from typing import List, Optional

import dateutil.parser
from dateutil.relativedelta import relativedelta

RFC1123_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"
INFRACTION_FORMAT = "%Y-%m-%d %H:%M"
TIME_MARKS = (
    (60, 'second'),  # 1 minute
    (60, 'minute'),  # 1 hour
    (24, 'hour'),  # 1 day
    (7, 'day'),  # 1 week
    (4, 'week'),  # 1 month
    (12, 'month'),  # 1 year
    (999, 'year')  # dumb the rest as year, max 999
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
    if value == 1:
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


def get_duration(date_from: datetime.datetime, date_to: datetime.datetime) -> str:
    """
    Get the duration between two datetime, in human readable format.

    Will return the two biggest units avaiable, for example:
    - 11 hours, 59 minutes
    - 1 week, 6 minutes
    - 7 months, 2 weeks
    - 3 years, 3 months
    - 5 minutes

    :param date_from: A datetime.datetime object.
    :param date_to: A datetime.datetime object.
    """
    div = abs(date_from - date_to).total_seconds()
    div = round(div, 0)  # to avoid (14 minutes, 60 seconds)
    results: List[str] = []
    for unit, name in TIME_MARKS:
        div, amount = divmod(div, unit)
        if amount > 0:
            plural = 's' if amount > 1 else ''
            results.append(f"{amount:.0f} {name}{plural}")
    # We have to reverse the order of units because currently it's smallest -> largest
    return ', '.join(results[::-1][:2])


def get_duration_from_expiry(expiry: str, date_from: datetime = None) -> str:
    """
    Get the duration between datetime.utcnow() and an expiry, in human readable format.

    Will return the two biggest units avaiable, for example:
    - 11 hours, 59 minutes
    - 1 week, 6 minutes
    - 7 months, 2 weeks
    - 3 years, 3 months
    - 5 minutes

    :param expiry: A string.
    """
    date_from = date_from or datetime.datetime.utcnow()
    date_to = dateutil.parser.isoparse(expiry).replace(tzinfo=None)
    return get_duration(date_from, date_to)
