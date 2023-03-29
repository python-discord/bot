---
embed:
    title: "Type hints"
---
A type hint indicates what type a variable is expected to be.
```python
def add(a: int, b: int) -> int:
    return a + b
```
The type hints indicate that for our `add` function the parameters `a` and `b` should be integers, and the function should return an integer when called.

It's important to note these are just hints and are not enforced at runtime.

```python
add("hello ", "world")
```
The above code won't error even though it doesn't follow the function's type hints; the two strings will be concatenated as normal.

Third party tools like [mypy](https://mypy.readthedocs.io/en/stable/introduction.html) can validate your code to ensure it is type hinted correctly. This can help you identify potentially buggy code, for example it would error on the second example as our `add` function is not intended to concatenate strings.

[mypy's documentation](https://mypy.readthedocs.io/en/stable/builtin_types.html) contains useful information on type hinting, and for more information check out [this documentation page](https://typing.readthedocs.io/en/latest/index.html).
