---
embed:
    title: "List comprehensions"
---
Do you ever find yourself writing something like this?
```py
>>> squares = []
>>> for n in range(5):
...    squares.append(n ** 2)
[0, 1, 4, 9, 16]
```
Using list comprehensions can make this both shorter and more readable. As a list comprehension, the same code would look like this:
```py
>>> [n ** 2 for n in range(5)]
[0, 1, 4, 9, 16]
```
List comprehensions also get an `if` clause:
```py
>>> [n ** 2 for n in range(5) if n % 2 == 0]
[0, 4, 16]
```

For more info, see [this pythonforbeginners.com post](http://www.pythonforbeginners.com/basics/list-comprehensions-in-python).
