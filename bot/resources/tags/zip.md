---
embed:
    title: "The `zip` function"
---
The zip function allows you to iterate through multiple iterables simultaneously. It joins the iterables together, almost like a zipper, so that each new element is a tuple with one element from each iterable.

```py
letters = 'abc'
numbers = [1, 2, 3]
# list(zip(letters, numbers)) --> [('a', 1), ('b', 2), ('c', 3)]
for letter, number in zip(letters, numbers):
    print(letter, number)
```
The `zip()` iterator is exhausted after the length of the shortest iterable is exceeded. If you would like to retain the other values, consider using [itertools.zip_longest](https://docs.python.org/3/library/itertools.html#itertools.zip_longest).

For more information on zip, please refer to the [official documentation](https://docs.python.org/3/library/functions.html#zip).
