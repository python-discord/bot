---
embed:
    title: "Identity vs. equality"
---
Should I be using `is` or `==`?

To check if two objects are equal, use the equality operator (`==`).
```py
x = 5
if x == 5:
    print("x equals 5")
if x == 3:
    print("x equals 3")
# Prints 'x equals 5'
```
To check if two objects are actually the same thing in memory, use the identity comparison operator (`is`).
```py
>>> list_1 = [1, 2, 3]
>>> list_2 = [1, 2, 3]
>>> if list_1 is [1, 2, 3]:
...    print("list_1 is list_2")
...
>>> reference_to_list_1 = list_1
>>> if list_1 is reference_to_list_1:
...    print("list_1 is reference_to_list_1")
...
list_1 is reference_to_list_1
```
