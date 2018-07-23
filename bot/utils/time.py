from dateutil.relativedelta import relativedelta


def _plural_timestring(value: int, unit: str) -> str:
    """
    Takes a value and a unit type,
    such as 24 and "hours".

    Returns a string that takes
    the correct plural into account.

    >>> _plural_timestring(1, "seconds")
    "1 second"
    >>> _plural_timestring(24, "hours")
    "24 hours"
    """

    if value == 1:
        return f"{value} {unit[:-1]}"
    else:
        return f"{value} {unit}"


def humanize(delta: relativedelta, accuracy: str = "seconds") -> str:
    """
    This takes a relativedelta and
    returns a nice human readable string.

    "4 days, 12 hours and 1 second"

    :param delta: A dateutils.relativedelta.relativedelta object
    :param accuracy: The smallest unit that should be included.
    :return: A humanized string.
    """

    units = {
        "years": delta.years,
        "months": delta.months,
        "days": delta.days,
        "hours": delta.hours,
        "minutes": delta.minutes,
        "seconds": delta.seconds
    }

    # Add the time units that are >0, but stop at accuracy.
    time_strings = []
    for unit, value in units.items():
        if value:
            time_strings.append(_plural_timestring(value, unit))

        if unit == accuracy:
            break

    # Add the 'and' between the last two units
    if len(time_strings) > 1:
        time_strings[-1] = f"{time_strings[-2]} and {time_strings[-1]}"
        del time_strings[-2]

    return ", ".join(time_strings)
