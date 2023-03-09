---
embed:
    title: "Error handling"
---
A key part of the Python philosophy is to ask for forgiveness, not permission. This means that it's okay to write code that may produce an error, as long as you specify how that error should be handled. Code written this way is readable and resilient.
```py
try:
    number = int(user_input)
except ValueError:
    print("failed to convert user_input to a number. setting number to 0.")
    number = 0
```
You should always specify the exception type if it is possible to do so, and your `try` block should be as short as possible. Attempting to handle broad categories of unexpected exceptions can silently hide serious problems.
```py
try:
    number = int(user_input)
    item = some_list[number]
except:
    print("An exception was raised, but we have no idea if it was a ValueError or an IndexError.")
```
For more information about exception handling, see [the official Python docs](https://docs.python.org/3/tutorial/errors.html), or watch [Corey Schafer's video on exception handling](https://www.youtube.com/watch?v=NIWwJbo-9_8).
