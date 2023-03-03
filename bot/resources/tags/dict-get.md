---
embed:
    title: "The `dict.get` method"
---
Often while using dictionaries in Python, you may run into `KeyErrors`. This error is raised when you try to access a key that isn't present in your dictionary. Python gives you some neat ways to handle them.

The [`dict.get`](https://docs.python.org/3/library/stdtypes.html#dict.get) method will return the value for the key if it exists, and None (or a default value that you specify) if the key doesn't exist. Hence it will _never raise_ a KeyError.
```py
>>> my_dict = {"foo": 1, "bar": 2}
>>> print(my_dict.get("foobar"))
None
```
Below, 3 is the default value to be returned, because the key doesn't exist-
```py
>>> print(my_dict.get("foobar", 3))
3
```
Some other methods for handling `KeyError`s gracefully are the [`dict.setdefault`](https://docs.python.org/3/library/stdtypes.html#dict.setdefault) method and [`collections.defaultdict`](https://docs.python.org/3/library/collections.html#collections.defaultdict) (check out the `!defaultdict` tag).
