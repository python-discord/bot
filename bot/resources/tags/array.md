**Lists are not arrays**
Python lists are similar to arrays in C-style languages, but unlike C-style arrays, the size of a list can change and the elements can be of different types. In the context of Python, the word "array" usually refers to arrays from Numpy, which represent arrays in their mathematical sense.

This code example illustrates how similar-looking operations are different for lists and arrays.

```py
>>> from numpy import array
>>> my_list = [1, 2, 3]
>>> my_array = array([1, 2, 3])
>>> my_list * 2
[1, 2, 3, 1, 2, 3]  # reduplicates the list
>>> my_array * 2
array([1, 4, 6])  # multiplies each element by two
```
Be sure not to use the terms interchangeably.
