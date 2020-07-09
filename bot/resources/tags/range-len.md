Iterating over `range(len(...))` is a common approach to accessing each item in an ordered collection.
```py
for i in range(len(my_list)):
    do_something(my_list[i])
```
The pythonic syntax is much simpler, and is guaranteed to produce elements in the same order:
```py
for item in my_list:
    do_something(item)
```
Python has other solutions for cases when the index itself might be needed. To get the element at the same index from two or more lists, use [zip](https://docs.python.org/3/library/functions.html#zip). To get both the index and the element at that index, use [enumerate](https://docs.python.org/3/library/functions.html#enumerate).
