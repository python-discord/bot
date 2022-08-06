---
aliases: ["generators", "iterators", "yield"]
embed:
    title: "Generators and Iterators"
---

[Iterators](https://docs.python.org/3/glossary.html#term-iterator) are objects that support iteration.

[Generators](https://docs.python.org/3/glossary.html#term-generator) are extended Iterators, which provide a simple way to create Iterators using yield functions or expressions.

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

for num in foo:
    print(num)
\```

**More Information**

• Generators and Iterators can also be created as custom classes by implementing their required [methods](https://docs.python.org/3/library/collections.abc.html#collections-abstract-base-classes-1). The preferred way to do this is by extending the respective Abstract Base Classes within `collections.abc`.

• Check out the [Real python article](https://realpython.com/introduction-to-python-generators/) for a more in-depth view of Generators and their use-cases!
