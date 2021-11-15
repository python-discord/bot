**Type Hints**

A type hint indicates what type something is expected to be. For example,
```python
def add(a: int, b: int) -> int:
    return a + b
```
In this case, we have a function,`add`, with parameters `a` and `b`. The type hints indicate that the parameters and return type are all integers.

It's important to note these are just hints and have no runtime effect. For example,
```python
# Uh oh
add("hello ", "world")
```
This code won't error even though it doesn't follow the function's type hints. It will just concatenate the two strings.

Third party tools like [mypy](http://mypy-lang.org/) can enforce your type hints. Mypy would error in the second example.

For more info about type hints, check out [PEP 484](https://www.python.org/dev/peps/pep-0484/).
