import datetime

from dateutil.relativedelta import relativedelta


def _stringify_time_unit(value: int, unit: str):
    """
    Returns a string to represent a value and time unit,
    ensuring that it uses the right plural form of the unit.

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


def humanize_delta(delta: relativedelta, precision: str = "seconds", max_units: int = 6):
    """
    Returns a human-readable version of the relativedelta.

    :param delta:      A dateutil.relativedelta.relativedelta object
    :param precision:  The smallest unit that should be included.
    :param max_units:  The maximum number of time-units to return.

    :return:           A string like `4 days, 12 hours and 1 second`,
                       `1 minute`, or `less than a minute`.
    """

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


def time_since(past_datetime: datetime.datetime, precision: str = "seconds", max_units: int = 6):
    """
    Takes a datetime and returns a human-readable string that
    describes how long ago that datetime was.

    :param past_datetime:  A datetime.datetime object
    :param precision:      The smallest unit that should be included.
    :param max_units:      The maximum number of time-units to return.

    :return:               A string like `4 days, 12 hours and 1 second ago`,
                           `1 minute ago`, or `less than a minute ago`.
    """

    now = datetime.datetime.utcnow()
    delta = abs(relativedelta(now, past_datetime))

    humanized = humanize_delta(delta, precision, max_units)

    return f"{humanized} ago"
