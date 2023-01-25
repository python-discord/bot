**Out of Place** and **In Place**

- An "out of place" operation creates a new object, leaving the original object unchanged. 
- An "in place" operation modifies the original object, without creating a new one. These return None explicitly.

A prime example of these different ideas is `list.sort()` vs `sorted(...)`:

`list.sort()` can cause many errors within your code, one of the most common is shown below:

```py
a_list = [3, 1, 2]
a_new_list = a_list.sort() # This will be None
print(a_new_list[1]) # This will error
```

On the other hand, `sorted()` can also cause errors:

```py
a_list = [3, 1, 2]
sorted(a_list)
print(a_list[0]) # You may expect 1, but it will print 3
```

Both of these errors are an easy fixes.
