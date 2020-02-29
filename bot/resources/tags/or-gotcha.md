When checking if something is equal to one thing or another, you might think that this is possible:
```py
if favorite_fruit == 'grapefruit' or 'lemon':
    print("That's a weird favorite fruit to have.")
```
After all, that's how you would normally phrase it in plain English. In Python, however, you have to have _complete instructions on both sides of the logical operator_.

So, if you want to check if something is equal to one thing or another, there are two common ways:
```py
# Like this...
if favorite_fruit == 'grapefruit' or favorite_fruit == 'lemon':
    print("That's a weird favorite fruit to have.")

# ...or like this.
if favorite_fruit in ('grapefruit', 'lemon'):
    print("That's a weird favorite fruit to have.")
```