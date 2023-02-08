**Out of Place** and **In Place**

In programming, there are two types of operations: "out of place" operations create a new object, leaving the original object unchanged. "in place" operations modify the original object, without creating a new one. These operations return None explicitly.

A common example of these different concepts is seen in the use of the methods `list.sort()` and `sorted(...)`. Using `list.sort()` and attempting to access an element of the list will result in an error. 

```py
# WRONG:

unsorted_list = [3, 1, 2]
sorted_list = unsorted_list.sort() # This will be None
print(sorted_list)  # Outputs None. Where did the list go?

list_to_sort = [3, 1, 2]
sorted(list_to_sort)
print(list_to_sort)  # The list still isn't sorted. Why?
```

To avoid these errors and unexpected results, it is required to assign the result of `sorted(...)` to a new variable and use `list.sort()` method in the original list. This way, the original list will be sorted and the new list will be created with the sorted elements.
