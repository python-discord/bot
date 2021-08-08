**Lists vs Arrays**
Python lists are similar to arrays in C-style languages, but unlike C-style arrays, the size of a list can change and the elements can be of different types.

This distinction is especially important in scientific computing, where an array would usually refer to a numpy array, which behaves differently to a list.

```py
>>> from numpy import array
>>> my_list = [1, 2, 3]
>>> my_array = array([1, 2, 3])
>>> my_list * 2
[1, 2, 3, 1, 2, 3]  # reduplicates the list
>>> my_array * 2
array([1, 4, 6])  # multiplies each element by two
```
