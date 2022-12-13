**Use cases of Underscore in Python**

- **Dunders**: Double Underscore (Dunder) methods are special methods defined in a class that are invoked implicitly. For example, `__name__`,`__init__`,`__repr__`, and `__str__`.
Use the `!dunder-methods` tag to know more about these methods.
- **Single leading Underscore**:  They're used in front a variable, a function or a method name, which indicates that these objects are meant to be used internally, such as `_name`. However, these objects **can** still be accessed from outside.
- **Single Trailing Underscores**: They are used to avoid naming conflict while using a variable, which is a reserved keyword. Using a variable name as `class` will produce an error. To avoid this conflict, you can add a trailing underscore as a naming convention i.e. `class_`.
-  **Double leading underscores**: Double leading underscores are typically used for Name Mangling. Name mangling is a process by which the interpreter changes the attribute name to avoid naming collisions in subclasses. More details regarding Name Mangling can be found [here](https://www.geeksforgeeks.org/name-mangling-in-python/).
- **Store Expression Value**: Underscore(**_**) is used to store the value of last expression in an interpreter and can be used as a variable. Example:
```python
>>> _ # Using underscore without any previously executed expression or value assigned to underscore
    NameError: name '_' is not defined
>>> 1 + 1  # evaluating expression
    2
>>> _        # prints value of last executed expression
    2
>>> _ + 2
    4
>>> _ = 3  # Once assigned any value,Underscore doesn't store the value of last executed expression anymore
>>> 5 + 9
    14
>>> _
    3
```
-  **Ignore Values**: Underscores can also be used for variable assignments, but they are generally used that way to store values that will not be needed. It is known as `throwaway variable`.
 ```python
>>> a, *_, b = (3, 5, 2, 6, 2) # Ignore values when unpacking
>>> print(a, b, _)
    3 2 [5, 2, 6]
>>> for _ in range(10):  # Ignoring the Index
        do_something()
```
-  **Improve Readability**: They can also be used with numeric literals to improve readability of long numbers.
 ```python
>>> 1_00_000
    100000
```

**References**:
- [Towards Data Science](https://towardsdatascience.com/whats-the-meaning-of-single-and-double-underscores-in-python-3d27d57d6bd1)
- [GeeksforGeeks](https://www.geeksforgeeks.org/underscore-_-python/)
- [Data Camp](https://www.datacamp.com/tutorial/role-underscore-python)
