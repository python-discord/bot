**Python Generators**

A generator is a function that returns a sequence of values,
producing them on demand, i.e. without storing them in a list.

---

Often you'll need to return a list of values from a function.

Imagine how you would implement a function that behaves like `map`,
that is, it applies a function to each element in a list:
```python
def my_map(function, old_list):
    new_list = []
    for element in old_list:
        new_list.append(function(element))
    return new_list

for i in my_map(abs, [-1, -2, 3, -4]):
    print(i)
# 1, 2, 3, 4
```
However, there are two main issues with this approach:

1. Initializing a list, appending to it, and returning it is noisy boilerplate code.

2. You will have to compute the result (which might even be infinite) first. This can take a lot of time and memory.

All of this can be solved with a _generator_:
```python
def my_map(function, old_list):
    for element in old_list:
        yield function(element)
```

You can try to run the loop in the example, and it gives the same result.
