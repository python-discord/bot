---
aliases: ["generators", "iterators", "yield"]
embed:
    title: "Generators and Iterators"
---

[Iterators](https://docs.python.org/3/glossary.html#term-iterator) are objects that support iteration.

[Generators](https://docs.python.org/3/glossary.html#term-generator) are extended Iterators, which provide a simple way to create Iterators using yield functions or expressions.

**Generator Functions**

A generator function can be created by using one or more `yield` statements. Here is an example of how a `read_lines` function returning a `list` can instead use `yield` to return `Generator`
\```py
def read_lines(file_name):
    lines = []
    with open(file_name, "r") as f:
        for line in f:
            lines.append(line.strip())
    return lines

def read_lines(file_name):
    with open(file_name, "r") as f:
        for line in f:
            yield line.strip()
\```
Generators can be a memory-efficient alternative to lists in many situations.
**Generator Expressions**

Generators can also be created by `for` clauses inside [expressions](https://docs.python.org/3/glossary.html#term-generator-expression). This is similar to creating a list comprehension but using `()` instead of `[]`. You can use `if` `else` ternary operators as you would in other comprehension forms.

\```py
foo = (x * 2 for x in range(5))

for num in foo:
    print(num)
\```

**More Information**

• Generators and Iterators can also be created as custom classes by implementing their required [abstract methods](https://docs.python.org/3/library/collections.abc.html#collections-abstract-base-classes-1).

• Check out the [Real python article](https://realpython.com/introduction-to-python-generators/) for a more in-depth view of Generators and their use-cases!
