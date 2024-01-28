---
embed:
    title: "Mutable default arguments"
---
Default arguments in Python are evaluated *once* when the function is
**defined**, *not* each time the function is **called**. This means that if
you have a mutable default argument and mutate it, you will have
mutated that object for all future calls to the function as well.

For example, the following `append_one` function appends `1` to a list
and returns it. `foo` is set to an empty list by default.
```python
>>> def append_one(foo=[]):
...     foo.append(1)
...     return foo
...
```
See what happens when we call it a few times:
```python
>>> append_one()
[1]
>>> append_one()
[1, 1]
>>> append_one()
[1, 1, 1]
```
Each call appends an additional `1` to our list `foo`. It does not
receive a new empty list on each call, it is the same list everytime.

To avoid this problem, you have to create a new object every time the
function is **called**:
```python
>>> def append_one(foo=None):
...     if foo is None:
...         foo = []
...     foo.append(1)
...     return foo
...
>>> append_one()
[1]
>>> append_one()
[1]
```

**Note**:

- This behavior can be used intentionally to maintain state between
calls of a function (eg. when writing a caching function).  
- This behavior is not unique to mutable objects, all default
arguments are evaulated only once when the function is defined.
