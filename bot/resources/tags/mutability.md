---
embed:
    title: "Mutable vs immutable objects"
---
Imagine that you want to make all letters in a string upper case. Conveniently, strings have an `.upper()` method.

You might think that this would work:
```python
>>> greeting = "hello"
>>> greeting.upper()
'HELLO'
>>> greeting
'hello'
```

`greeting` didn't change. Why is that so?

That's because strings in Python are _immutable_. You can't change them, you can only pass around existing strings or create new ones.

```python
>>> greeting = "hello"
>>> greeting = greeting.upper()
>>> greeting
'HELLO'
```

`greeting.upper()` creates and returns a new string which is like the old one, but with all the letters turned to upper case.

`int`, `float`, `complex`, `tuple`, `frozenset` are other examples of immutable data types in Python.

Mutable data types like `list`, on the other hand, can be changed in-place:
```python
>>> my_list = [1, 2, 3]
>>> my_list.append(4)
>>> my_list
[1, 2, 3, 4]
```

Other examples of mutable data types in Python are `dict` and `set`. Instances of user-defined classes are also mutable.

For an in-depth guide on mutability see [Ned Batchelder's video on names and values](https://youtu.be/_AEJHKGk9ns/).
