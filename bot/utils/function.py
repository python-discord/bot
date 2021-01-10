"""Utilities for interaction with functions."""

import functools
import inspect
import types
import typing as t

Argument = t.Union[int, str]
BoundArgs = t.OrderedDict[str, t.Any]
Decorator = t.Callable[[t.Callable], t.Callable]
ArgValGetter = t.Callable[[BoundArgs], t.Any]


def get_arg_value(name_or_pos: Argument, arguments: BoundArgs) -> t.Any:
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


def get_arg_value_wrapper(
    decorator_func: t.Callable[[ArgValGetter], Decorator],
    name_or_pos: Argument,
    func: t.Callable[[t.Any], t.Any] = None,
) -> Decorator:
    """
    Call `decorator_func` with the value of the arg at the given name/position.

    `decorator_func` must accept a callable as a parameter to which it will pass a mapping of
    parameter names to argument values of the function it's decorating.

    `func` is an optional callable which will return a new value given the argument's value.

    Return the decorator returned by `decorator_func`.
    """
    def wrapper(args: BoundArgs) -> t.Any:
        value = get_arg_value(name_or_pos, args)
        if func:
            value = func(value)
        return value

    return decorator_func(wrapper)


def get_bound_args(func: t.Callable, args: t.Tuple, kwargs: t.Dict[str, t.Any]) -> BoundArgs:
    """
    Bind `args` and `kwargs` to `func` and return a mapping of parameter names to argument values.

    Default parameter values are also set.
    """
    sig = inspect.signature(func)
    bound_args = sig.bind(*args, **kwargs)
    bound_args.apply_defaults()

    return bound_args.arguments


def update_wrapper_globals(wrapper: types.FunctionType, wrapped: types.FunctionType) -> types.FunctionType:
    """
    Update globals of `wrapper` with the globals from `wrapped`.

    For forwardrefs in command annotations discordpy uses the __global__ attribute of the function
    to resolve their values, with decorators that replace the function this breaks because they have
    their own globals.

    This function creates a new function functionally identical to `wrapper`, which has the globals replaced with
    a merge of `wrapped`s globals and the `wrapper`s globals.

    In case a global name from `wrapped` conflicts with a name from `wrapper`'s globals, `wrapper` will win
    to keep it functional, but this may cause problems if the name is used as an annotation and
    discord.py uses it as a converter on a parameter from `wrapped`.
    """
    new_globals = wrapper.__globals__.copy()
    new_globals.update((k, v) for k, v in wrapped.__globals__.items() if k not in wrapper.__code__.co_names)
    return types.FunctionType(
        code=wrapper.__code__,
        globals=new_globals,
        name=wrapper.__name__,
        argdefs=wrapper.__defaults__,
        closure=wrapper.__closure__,
    )


def command_wraps(
        wrapped: types.FunctionType,
        assigned: t.Sequence[str] = functools.WRAPPER_ASSIGNMENTS,
        updated: t.Sequence[str] = functools.WRAPPER_UPDATES,
) -> t.Callable[[types.FunctionType], types.FunctionType]:
    """Update `wrapped` to look like the decorated function and update globals for discordpy forwardref evaluation."""
    def decorator(wrapper: types.FunctionType) -> types.FunctionType:
        return functools.update_wrapper(
            update_wrapper_globals(wrapper, wrapped), wrapped, assigned, updated
        )

    return decorator
