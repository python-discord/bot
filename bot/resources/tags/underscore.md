---
aliases: ["under"]
embed:
    title: "Meanings of underscores in identifier names"
---

- `__name__`: Used to implement special behaviour, such as the `+` operator for classes with the `__add__` method. [More info](https://dbader.org/blog/python-dunder-methods)
- `_name`: Indicates that a variable is "private" and should only be used by the class or module that defines it
- `name_`: Used to avoid naming conflicts. For example, as `class` is a keyword, you could call a variable `class_` instead
- `__name`: Causes the name to be "mangled" if defined inside a class. [More info](https://docs.python.org/3/tutorial/classes.html#private-variables)

A single underscore, **`_`**, has multiple uses:
- To indicate an unused variable, e.g. in a for loop if you don't care which iteration you are on
```python
for _ in range(10):
    print("Hello World")
```
-  In the REPL, where the previous result is assigned to the variable `_`
```python
>>> 1 + 1  # Evaluated and stored in `_`
    2
>>> _ + 3  # Take the previous result and add 3
    5
```
- In integer literals, e.g. `x = 1_500_000` can be written instead of `x = 1500000` to improve readability

See also ["Reserved classes of identifiers"](https://docs.python.org/3/reference/lexical_analysis.html#reserved-classes-of-identifiers) in the Python docs, and [this more detailed guide](https://dbader.org/blog/meaning-of-underscores-in-python).
