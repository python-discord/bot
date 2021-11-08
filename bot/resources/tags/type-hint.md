**Type Hints**

A typehint indicates what type something should be. For example,
```python
def add(a: int, b: int) -> int:
    sum: int = a + b
    return sum
```
In this case, `a` and `b` are expected to be ints, and the function returns an int. We also declare an intermediate variable `sum`, which we indicate to be an int.

It's important to note these are just hints and have no runtime effect. For example,
```python
#uh oh
add("hello ", "world")
```
This code will run without error, even though it doesn't follow the function's type hints.
