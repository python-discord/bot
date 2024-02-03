---
embed:
    title: "Comparisons to `True` and `False`"
---
It's tempting to think that if statements always need a comparison operator like `==` or `!=`, but this isn't true.
If you're just checking if a value is truthy or falsey, you don't need `== True` or `== False`.
```py
# instead of this...
if user_input.startswith('y') == True:
    my_func(user_input)

# ...write this
if user_input.startswith('y'):
    my_func(user_input)

# for false conditions, instead of this...
if user_input.startswith('y') == False:
    my_func(user_input)

# ...just use `not`
if not user_input.startswith('y'):
    my_func(user_input)
```
This also applies to expressions that use `is True` or `is False`.
