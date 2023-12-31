---
embed:
    title: "Naming and binding"
---
A name is a piece of text that is bound to an object. They are a **reference** to an object. Examples are function names, class names, module names, variables, etc.

**Note:** Names **cannot** reference other names, and assignment **never** creates a copy.
```py
x = 1  # x is bound to 1
y = x  # y is bound to VALUE of x
x = 2  # x is bound to 2
print(x, y) # 2 1
```
When doing `y = x`, the name `y` is being bound to the *value* of `x` which is `1`. Neither `x` nor `y` are the 'real' name. The object `1` simply has *multiple* names. They are the exact same object.
```
>>> x = 1
x ━━ 1

>>> y = x
x ━━ 1
y ━━━┛

>>> x = 2
x ━━ 2
y ━━ 1
```
**Names are created in multiple ways**  
You might think that the only way to bind a name to an object is by using assignment, but that isn't the case. All of the following work exactly the same as assignment:  
- `import` statements  
- `class` and `def`  
- `for` loop headers  
- `as` keyword when used with `except`, `import`, and `with`  
- formal parameters in function headers  

There is also `del` which has the purpose of *unbinding* a name.

**More info**  
- Please watch [Ned Batchelder's talk](https://youtu.be/_AEJHKGk9ns) on names in python for a detailed explanation with examples  
- [Official documentation](https://docs.python.org/3/reference/executionmodel.html#naming-and-binding)
