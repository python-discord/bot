**Positional vs. Keyword arguments**

Functions can take two different kinds of arguments. A positional argument is just the object itself. A keyword argument is a name assigned to an object.

**Example**
```py
>>> print('Hello', 'world!', sep=', ')
Hello, world!
```
The first two strings `'Hello'` and `world!'` are positional arguments.
The `sep=', '` is a keyword argument.

**Note**
A keyword argument can be passed positionally in some cases.
```py
def sum(a, b=1):
    return a + b

sum(1, b=5)
sum(1, 5) # same as above
```
[Somtimes this is forced](https://www.python.org/dev/peps/pep-0570/#history-of-positional-only-parameter-semantics-in-python), in the case of the `pow()` function.

The reverse is also true:
```py
>>> def foo(a, b):
...     print(a, b)
...
>>> foo(a=1, b=2)
1 2
>>> foo(b=1, a=2)
2 1
```

**More info**  
• [Keyword only arguments](https://www.python.org/dev/peps/pep-3102/)  
• [Positional only arguments](https://www.python.org/dev/peps/pep-0570/)  
• `!tags param-arg` (Parameters vs. Arguments)  
