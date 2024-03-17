import contextlib
import functools
import pkgutil
import unittest.mock
from collections.abc import Callable


@functools.wraps(unittest.mock._patch.decoration_helper)
@contextlib.contextmanager
def _decoration_helper(self, patched, args, keywargs):
    """Skips adding patchings as args if their `dont_pass` attribute is True."""
    # Don't ask what this does. It's just a copy from stdlib, but with the dont_pass check added.
    extra_args = []
    with contextlib.ExitStack() as exit_stack:
        for patching in patched.patchings:
            arg = exit_stack.enter_context(patching)
            if not getattr(patching, "dont_pass", False):
                # Only add the patching as an arg if dont_pass is False.
                if patching.attribute_name is not None:
                    keywargs.update(arg)
                elif patching.new is unittest.mock.DEFAULT:
                    extra_args.append(arg)

        args += tuple(extra_args)
        yield args, keywargs


@functools.wraps(unittest.mock._patch.copy)
def _copy(self):
    """Copy the `dont_pass` attribute along with the standard copy operation."""
    patcher_copy = _copy.original(self)
    patcher_copy.dont_pass = getattr(self, "dont_pass", False)
    return patcher_copy


# Monkey-patch the patcher class :)
_copy.original = unittest.mock._patch.copy
unittest.mock._patch.copy = _copy
unittest.mock._patch.decoration_helper = _decoration_helper


def autospec(target, *attributes: str, pass_mocks: bool = True, **patch_kwargs) -> Callable:
    """
    Patch multiple `attributes` of a `target` with autospecced mocks and `spec_set` as True.

    If `pass_mocks` is True, pass the autospecced mocks as arguments to the decorated object.
    """
    # Caller's kwargs should take priority and overwrite the defaults.
    kwargs = dict(spec_set=True, autospec=True)
    kwargs.update(patch_kwargs)

    # Import the target if it's a string.
    # This is to support both object and string targets like patch.multiple.
    if isinstance(target, str):
        target = pkgutil.resolve_name(target)

    def decorator(func):
        for attribute in attributes:
            patcher = unittest.mock.patch.object(target, attribute, **kwargs)
            if not pass_mocks:
                # A custom attribute to keep track of which patchings should be skipped.
                patcher.dont_pass = True
            func = patcher(func)
        return func
    return decorator
