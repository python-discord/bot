---
embed:
    title: "The or-gotcha"
---
When checking if something is equal to one thing or another, you might think that this is possible:
```py
# Incorrect...
if favorite_fruit == 'grapefruit' or 'lemon':
    print("That's a weird favorite fruit to have.")
```
While this makes sense in English, it may not behave the way you would expect. In Python, you should have _[complete instructions on both sides of the logical operator](https://docs.python.org/3/reference/expressions.html#boolean-operations)_.

So, if you want to check if something is equal to one thing or another, there are two common ways:
```py
# Like this...
if favorite_fruit == 'grapefruit' or favorite_fruit == 'lemon':
    print("That's a weird favorite fruit to have.")

# ...or like this.
if favorite_fruit in ('grapefruit', 'lemon'):
    print("That's a weird favorite fruit to have.")
```
