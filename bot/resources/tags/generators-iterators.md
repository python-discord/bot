**Generators and Iterators**

What is a generator and an iterator and what is the difference between each other?

**Generator**

A generator yields one item at a time and generates items only when in demand and can be created with a function that may contain a `yield` or sometimes `return` statements, but they're not bound to functions as you can subclass [collections.abc.Generator](https://docs.python.org/3/library/collections.abc.html#collections.abc.Generator), a generator can also be an expression(genexpr).
```py
>>> print(num for num in range(11))
<generator object <genexpr> at 0x0000000000000000>
```

How is a generator any different from a list, for example?
The generator yields one item at a time and generates items only when in demand. Whereas, in a list, Python reserves memory for the whole list.

**Iterator**

An iterator is any object whose class has `__next__` and `__iter__` methods. An iterator can also be created with the built-in function `iter`

```py
from typing import NoReturn


class Foo:
    def __init__(self, max: int = 0) -> None:
        self.max = max

    def __iter__(self) -> "Foo":
        self.n = 0
        return self

    def __next__(self) -> int | NoReturn:
        if self.n <= self.max:
            result = 2**self.n
            self.n += 1
            return result
        else:
            raise StopIteration
```
The `StopIteration` exception must be raised or the iterator is pronounced broken.

**What is the difference between iterators and generators?**

All Generators are Iterators, the abstract base class for a `Generator` actually inherits `Iterator`. `Generator` actually requires 2 methods to be implemented over an `Iterator`'s `__next__` and `__iter__`, which are `send`, `throw`, and the mix-in methods `close`, the only difference of a `Generator` and an `Iterator` are there use cases and implementation.

More info here: [collections.abc](https://docs.python.org/3/library/collections.abc.html)
