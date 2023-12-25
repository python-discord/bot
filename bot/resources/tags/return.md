---
embed:
    title: "Return statement"
---
A value created inside a function can't be used outside of it unless you `return` it.

Consider the following function:
```py
def square(n):
    return n * n
```
If we wanted to store 5 squared in a variable called `x`, we would do:
`x = square(5)`. `x` would now equal `25`.

**Common Mistakes**
```py
>>> def square(n):
...     n * n  # calculates then throws away, returns None
...
>>> x = square(5)
>>> print(x)
None
>>> def square(n):
...     print(n * n)  # calculates and prints, then throws away and returns None
...
>>> x = square(5)
25
>>> print(x)
None
```
**Things to note**  
- `print()` and `return` do **not** accomplish the same thing. `print()` will show the value, and then it will be gone.  
- A function will return `None` if it ends without a `return` statement.  
- When you want to print a value from a function, it's best to return the value and print the *function call* instead, like `print(square(5))`.
