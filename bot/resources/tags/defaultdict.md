---
embed:
    title: "The `collections.defaultdict` class"
---
The Python `defaultdict` type behaves almost exactly like a regular Python dictionary, but if you try to access or modify a missing key, the `defaultdict` will automatically insert the key and generate a default value for it.
While instantiating a `defaultdict`, we pass in a function that tells it how to create a default value for missing keys.

```py
>>> from collections import defaultdict
>>> my_dict = defaultdict(int)
>>> my_dict
defaultdict(<class 'int'>, {})
```

In this example, we've used the `int` class which returns 0 when called like a function, so any missing key will get a default value of 0. You can also get an empty list by default with `list` or an empty string with `str`.

```py
>>> my_dict["foo"]
0
>>> my_dict["bar"] += 5
>>> my_dict
defaultdict(<class 'int'>, {'foo': 0, 'bar': 5})
```
Check out the [`docs`](https://docs.python.org/3/library/collections.html#collections.defaultdict) to learn even more!
