**[`collections.defaultdict`](https://docs.python.org/3/library/collections.html#collections.defaultdict)**

The Python `defaultdict` type behaves almost exactly like a regular Python dictionary, but if you try to access or modify a missing key, the `defaultdict` will automatically create the key and generate a default value for it.
While instantiating a `defaultdict`, we pass in a function that tells it how to create a default value for missing keys.

```py
>>> from collections import defaultdict
>>> my_dict = defaultdict(int, {"foo": 1, "bar": 2})
>>> print(my_dict)
defaultdict(<class 'int'>, {'foo': 1, 'bar': 2})
```

In this example, we've used the `int` function - this means that if we try to access a non-existent key, it provides the default value of 0.

```py
>>> print(my_dict["foobar"])
0
>>> print(my_dict)
defaultdict(<class 'int'>, {'foo': 1, 'bar': 2, 'foobar': 0})
```
