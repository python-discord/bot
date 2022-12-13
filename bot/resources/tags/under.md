**Use cases of Underscore in Python**

- **Dunders**: Double Underscore (Dunder) methods are special methods defined in a class that are invoked implicitly. For example, `__name__`,`__init__`,`__repr__`, and `__str__`.
Use the `!dunder-methods` tag to know more about these methods
- **Single leading Underscore**:  In front of a variable, a function, or a method name means that these objects are used internally, such as `_name`. Remember that these objects can be accessed outside or other script.
- **Single leading Underscore**:  In front of a variable, a function, or a method name means that these objects are used internally, such as `_name`. However, remember that these objects **can** be accessed outside.
-  **Double leading underscores**: Double leading underscores are typically used for name mangling.
Name mangling is a process by which the interpreter changes the attribute name to avoid naming collisions in subclasses.[GeeksforGeeks](https://www.geeksforgeeks.org/name-mangling-in-python/)
- **Store Expression Value** Underscore(**_**) is used to store the value of last expression in an interpreter and can be used as a variable. Example:
```python
>>> 1 + 1
    2
>>> _
    2
>>> _ + 2
    4
```
-  **Ignore Values**: Underscores can also be used for variable assignments, but they are generally used to store values that will not be needed.It is known as `throwaway variable`
 ```python
>>> a, *_, b = (3, 5, 2, 6, 2) # Ignore values when unpacking
>>> print(a, b, _)
    3 2 [5, 2, 6]
>>> for _ in range(10):  # Ignoring the Index
        do_something()
```
-  **Improve Readability**: they can also be used with numeric literals to improve readability of long numbers.
 ```python
>>> 1_00_000
    100000
```

**References**:
- [Towards Data Science](https://towardsdatascience.com/whats-the-meaning-of-single-and-double-underscores-in-python-3d27d57d6bd1)
- [GeeksforGeeks](https://www.geeksforgeeks.org/underscore-_-python/)
- [Data Camp](https://www.datacamp.com/tutorial/role-underscore-python)
