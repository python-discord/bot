**Mutable vs immutable objects**

Imagine that you want to make all letters in a string upper case.
Conveniently, strings have an `.upper()` method.

You might think that this would work:
```python
string = "abcd"
string.upper()
print(string) # abcd
```

`string` didn't change. Why is that so?

That's because strings in Python are _immutable_. You can't change them, you can only pass
around existing strings or create new ones.

```python
string = "abcd"
string = string.upper()
```
`string.upper()` creates a new string which is like the old one, but with all
the letters turned to upper case.

`int`, `float`, `complex`, `tuple`, `frozenset`  are other examples of immutable data types in Python.

Mutable data types like `list`, on the other hand, can be changed in-place:
```python
my_list = [1, 2, 3]
my_list.append(4)
print(my_list) # [1, 2, 3, 4]
```

`dict` and `set` are other examples of mutable data types in Python.
