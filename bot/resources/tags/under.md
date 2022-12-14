**Use cases of Underscore in Python**

- **Dunders**: Double Underscore (Dunder) methods are special methods defined in a class that are invoked implicitly. For example, `__name__`,`__init__`,`__repr__`, and `__str__`.
Use the `!dunder-methods` tag to know more about them.
- **Single Leading Underscores**:  They're used in front a variable, a function or a method name, which indicates that these objects are meant to be used internally, such as `_name`. However, these objects **can** still be accessed from outside.
- **Single Trailing Underscores**: They are used to avoid naming conflict while making a new variable whose name might conflict with a reserved keyword or package name, etc. For example, using `class` as a variable name will produce an error; and to avoid this conflict, you can add a trailing underscore to it, i.e. `class_`.
-  **Double Leading Underscores**: Double leading underscores are typically used for "Name Mangling". Name mangling is a process by which the interpreter changes the attribute name to avoid naming collisions in subclasses. More details regarding this topic can be found [here](https://www.geeksforgeeks.org/name-mangling-in-python/).
- **Store Expression Value**: Underscore(**_**) is used to store the value of last expression in an interpreter and can be used as a variable. Example:
```python
>>> _ # Using underscore without any previously executed expression or value assigned to underscore.
    NameError: name '_' is not defined
>>> 1 + 1  # evaluating expression.
    2
>>> _        # Prints the value of the last executed expression.
    2
>>> _ + 2
    4
>>> _ = 3  # Once a value has explicitly been assigned to it, underscore won't store the value of last executed expression anymore.
>>> 5 + 9
    14
>>> _
    3
```
-  **Ignore Values**: We previously stated that underscores can also be used for variable assignments, but they are most commonly used to store values that will not be needed. Therefore,they are also known as `throwaway variable`.
 ```python
>>> a, *_, b = (3, 5, 2, 6, 2) # Ignore values when unpacking.
>>> print(a, b, _)
    3 2 [5, 2, 6]
>>> for _ in range(10):  # Here the index is ignored since we only want to execute the same function multiple times.
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
