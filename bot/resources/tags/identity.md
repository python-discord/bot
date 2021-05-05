**Identity vs. Equality**

Should I be using `is` or `==`?

To check if two things are equal, use the equality operator (`==`).
```py
x = 5
if x == 5:
    print("x equals 5")
if x == 3:
    print("x equals 3")
# Prints 'x equals 5'
```
To check if two things are actually the same thing in memory, use the identity comparison operator (`is`).
```py
x = [1, 2, 3]
y = [1, 2, 3]
if x is [1, 2, 3]:
    print("x is y")
z = x
if x is z:
    print("x is z")
# Prints 'x is z'
```
