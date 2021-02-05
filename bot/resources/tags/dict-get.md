Often while using dictionaries in Python, you may run into `KeyErrors`. This error is raised when you try to access a key that isn't present in your dictionary.\
While you can use a `try` and `except` block to catch the `KeyError`, Python also gives you some other neat ways to handle them.
__**The `dict.get` method**__
The [`dict.get`](https://docs.python.org/3/library/stdtypes.html#dict.get) method will return the value for the key if it exists, or None (or a default value that you specify) if the key doesn't exist. Hence it will _never raise_ a KeyError.
```py
>>> my_dict = {"foo": 1, "bar": 2}
>>> print(my_dict.get("foobar"))
None
>>> print(my_dict.get("foobar", 3))    # here 3 is the default value to be returned, in case the key doesn't exist
3
```

Some other methods that can be used for handling KeyErrors gracefully are the [`dict.setdefault`](https://docs.python.org/3/library/stdtypes.html#dict.setdefault) method, or by using [`collections.defaultdict`](https://docs.python.org/3/library/collections.html#collections.defaultdict).
