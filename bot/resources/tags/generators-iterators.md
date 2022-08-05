**Generators and Iterators**

What is a generator and an iterator and what is the difference between each other?

**Generator**

A generator is a function that may contain a `yield` or sometimes `return` statements, a generator can also be an expression(genexpr).
```py
>>> print(num for num in range(11))
<generator object <genexpr> at 0x0000000000000000>
```

Well, what does a generator do and what is it any different from a list, for example?
The generator yields one item at a time and generates items only when in demand. Whereas, in a list, Python reserves memory for the whole list. A generator can be an iterator but not vice versa.


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

An iterator requires a `__next__` and `__iter__` methods over a generator that only needs an `__iter__` method.
