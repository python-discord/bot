---
embed:
    title: "Pythonic way of iterating over ordered collections"
---
Beginners often iterate over `range(len(...))` because they look like Java or C-style loops, but this is almost always a bad practice in Python.
```py
for i in range(len(my_list)):
    do_something(my_list[i])
```
It's much simpler to iterate over the list (or other sequence) directly:
```py
for item in my_list:
    do_something(item)
```
Python has other solutions for cases when the index itself might be needed. To get the element at the same index from two or more lists, use [zip](https://docs.python.org/3/library/functions.html#zip). To get both the index and the element at that index, use [enumerate](https://docs.python.org/3/library/functions.html#enumerate).
