**Out of Place** and **In Place**

- An "out of place" operation creates a new object, leaving the original object unchanged. 
- An "in place" operation modifies the original object, without creating a new one. These return None explicitly.

A prime example of these different ideas is `list.sort()` vs `sorted(...)`:

This is a common use for `list.sort()` which will end in an error.

```py
a_list = [3, 1, 2]
a_new_list = a_list.sort() # This will be None
print(a_new_list[1]) # This will error
```

This is a common use for `sorted()` which will end in a unexpected result.

```py
a_list = [3, 1, 2]
sorted(a_list)
print(a_list[0]) # You may expect 1, but it will print 3
```

To fix this you just need to set a new variable to `sorted(a_list)`, and don't create a new list for `list.sort()`
