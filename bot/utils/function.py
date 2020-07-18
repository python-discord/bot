"""Utilities for interaction with functions."""

import typing as t

Argument = t.Union[int, str]


def get_arg_value(name_or_pos: Argument, arguments: t.OrderedDict[str, t.Any]) -> t.Any:
    """
    Return a value from `arguments` based on a name or position.

    `arguments` is an ordered mapping of parameter names to argument values.

    Raise TypeError if `name_or_pos` isn't a str or int.
    Raise ValueError if `name_or_pos` does not match any argument.
    """
    if isinstance(name_or_pos, int):
        # Convert arguments to a tuple to make them indexable.
        arg_values = tuple(arguments.items())
        arg_pos = name_or_pos

        try:
            name, value = arg_values[arg_pos]
            return value
        except IndexError:
            raise ValueError(f"Argument position {arg_pos} is out of bounds.")
    elif isinstance(name_or_pos, str):
        arg_name = name_or_pos
        try:
            return arguments[arg_name]
        except KeyError:
            raise ValueError(f"Argument {arg_name!r} doesn't exist.")
    else:
        raise TypeError("'arg' must either be an int (positional index) or a str (keyword).")
