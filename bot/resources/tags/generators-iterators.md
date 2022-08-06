---
aliases: ["generators", "iterators", "yield"]
embed:
    title: "Generators and Iterators"
---

[Iterators](https://docs.python.org/3/glossary.html#term-iterator) are objects that support iteration. Specifically, they need to implement the `__iter__` and `__next__` special methods and raise `StopIteration` when there are no values to be returned.

Built-in functions such as [zip](https://docs.python.org/3/library/functions.html#zip) and [map](https://docs.python.org/3/library/functions.html#map) return Iterators, this allows lazy, or memory-efficient, iteration as the elements do not need to be pre-computed before being used.

[Generators](https://docs.python.org/3/glossary.html#term-generator) are extended Iterators, which provide a simple way to create objects that function like Iterators by using yield functions or expressions.

**Generator Functions**

A generator function can be created by using one or more `yield` statements. 
\```py
def foo():
    yield 1
    yield 2
\```
When called, this function returns a Generator. Code within the generator does not execute immediately when a Generator is created.
\```py
foo()
<generator object foo at 0x1>
\```
Generator results can be accessed by iteration with `for`, or using `next()`. When calling `next()` on a Generator, the function will run until it reaches the next yield, then pause and yield the result. Further code does not execute until the next `yield` is reached. If the Generator is exhausted, a `StopIteration` Exception is raised.
\```py
x = foo()
next(x) -> 1
next(x) -> 2
next(x) -> StopIteration
\```
**Generator Expressions**

Generators can also be created by `for` clauses inside [expressions](https://docs.python.org/3/glossary.html#term-generator-expression). This is similar to creating a list comprehension but using `()` instead of `[]`. You can use `if` `else` ternary operators as you would in other comprehension forms.

\```py
foo = (x * 2 for x in range(5))
bar = sum(x * 2 for x in range(5))
\```

Note that Generators created using expressions are not functions that return Generators, rather, they are already Generator objects. You can only iterate the contents of `foo` once before it is exhausted.
\```py
list(foo) -> [0, 2, 4, 6, 8]
list(foo) -> []
\```

You can also use `*` to unpack Generators as positional arguments for functions, like any other Iterable object.
\```py
print(*foo) -> 0 2 4 6 8
\```
**What is the difference between iterators and generators?**

All Generators are Iterators, the abstract base class for a `Generator` actually inherits `Iterator`. `Generator` actually requires 2 methods to be implemented over an `Iterator`'s `__next__` and `__iter__`, which are `send`, `throw`, and the mix-in methods `close`, the only difference of a `Generator` and an `Iterator` are there use cases and implementation.

More info here: [collections.abc](https://docs.python.org/3/library/collections.abc.html)
