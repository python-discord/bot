---
embed:
    title: "Star / Wildcard imports"
---

Wildcard imports are import statements in the form `from <module_name> import *`. What imports like these do is that they import everything **[1]** from the module into the current module's namespace **[2]**. This allows you to use names defined in the imported module without prefixing the module's name.

Example:
```python
>>> from math import *
>>> sin(pi / 2)
1.0
```
**This is discouraged, for various reasons:**

Example:
```python
>>> from custom_sin import sin
>>> from math import *
>>> sin(pi / 2)  # uses sin from math rather than your custom sin
```
- Potential namespace collision. Names defined from a previous import might get shadowed by a wildcard import.
- Causes ambiguity. From the example, it is unclear which `sin` function is actually being used. From the Zen of Python **[3]**: `Explicit is better than implicit.`
- Makes import order significant, which they shouldn't. Certain IDE's `sort import` functionality may end up breaking code due to namespace collision.

**How should you import?**

- Import the module under the module's namespace (Only import the name of the module, and names defined in the module can be used by prefixing the module's name)
```python
>>> import math
>>> math.sin(math.pi / 2)
```
- Explicitly import certain names from the module
```python
>>> from math import sin, pi
>>> sin(pi / 2)
```
Conclusion: Namespaces are one honking great idea -- let's do more of those! *[3]*

**[1]** If the module defines the variable `__all__`, the names defined in `__all__` will get imported by the wildcard import, otherwise all the names in the module get imported (except for names with a leading underscore)
**[2]** [Namespaces and scopes](https://www.programiz.com/python-programming/namespace)
**[3]** [Zen of Python](https://peps.python.org/pep-0020/)
