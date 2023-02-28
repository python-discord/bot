---
embed:
    title: "The strip-gotcha"
---
When working with `strip`, `lstrip`, or `rstrip`, you might think that this would be the case:
```py
>>> "Monty Python".rstrip(" Python")
"Monty"
```
While this seems intuitive, it would actually result in:
```py
"M"
```
as Python interprets the argument to these functions as a set of characters rather than a substring.

If you want to remove a prefix/suffix from a string, `str.removeprefix` and `str.removesuffix` are recommended and were added in 3.9.
```py
>>> "Monty Python".removesuffix(" Python")
"Monty"
```
See the documentation of [str.removeprefix](https://docs.python.org/3.10/library/stdtypes.html#str.removeprefix) and [str.removesuffix](https://docs.python.org/3.10/library/stdtypes.html#str.removesuffix) for more information.
