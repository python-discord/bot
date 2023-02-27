---
embed:
    title: "The `enumerate` function"
---
Ever find yourself in need of the current iteration number of your `for` loop? You should use **enumerate**! Using `enumerate`, you can turn code that looks like this:
```py
index = 0
for item in my_list:
    print(f"{index}: {item}")
    index += 1
```
into beautiful, _pythonic_ code:
```py
for index, item in enumerate(my_list):
    print(f"{index}: {item}")
```
For more information, check out [the official docs](https://docs.python.org/3/library/functions.html#enumerate), or [PEP 279](https://peps.python.org/pep-0279/).
