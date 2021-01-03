**Return Statement**

When calling a function, you'll often want it to give you a value back. In order to do that, you must `return` it. The reason for this is because functions have their own scope. Any values defined within the function body are inaccessible outside of that function.

*For more information about scope, see `!tags scope`*

Consider the following function:
```py
def square(n):
    return n*n
```
If we wanted to store 5 squared in a variable called `x`, we could do that like so:
`x = square(5)`. `x` would now equal `25`.

**Common Mistakes**
```py
>>> def square(n):
...     n*n  # calculates then throws away, returns None
...
>>> x = square(5)
>>> print(x)
None
>>> def square(n):
...     print(n*n)  # calculates and prints, then throws away and returns None
...
>>> x = square(5)
25
>>> print(x)
None
```
**Things to note**  
• `print()` and `return` do **not** accomplish the same thing. `print()` will only print the value, it will not be accessible outside of the function afterwards.  
• A function will return `None` if it ends without reaching an explicit `return` statement.  
• When you want to print a value calculated in a function, instead of printing inside the function, it is often better to return the value and print the *function call* instead.  
• [Official documentation for `return`](https://docs.python.org/3/reference/simple_stmts.html#the-return-statement)  
