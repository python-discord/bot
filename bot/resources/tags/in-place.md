---
embed:
    title: "In-place vs. Out-of-place operations"
---

In programming, there are two types of operations:
- "In-place" operations, which modify the original object
- "Out-of-place" operations, which returns a new object and leaves the original object unchanged

For example, the `.sort()` method of lists is in-place, so it modifies the list you call `.sort()` on:
```python
>>> my_list = [5, 2, 3, 1]
>>> my_list.sort()  # Returns None
>>> my_list
[1, 2, 3, 5]
```
On the other hand, the `sorted()` function is out-of-place, so it returns a new list and leaves the original list unchanged:
```python
>>> my_list = [5, 2, 3, 1]
>>> sorted_list = sorted(my_list)
>>> sorted_list
[1, 2, 3, 5]
>>> my_list
[5, 2, 3, 1]
```
In general, methods of mutable objects tend to be in-place (since it can be expensive to create a new object), whereas operations on immutable objects are always out-of-place (since they cannot be modified).
