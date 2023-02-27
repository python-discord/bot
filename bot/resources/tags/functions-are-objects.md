---
embed:
    title: "Calling vs. referencing functions"
---
When assigning a new name to a function, storing it in a container, or passing it as an argument, a common mistake made is to call the function. Instead of getting the actual function, you'll get its return value.

In Python you can treat function names just like any other variable. Assume there was a function called `now` that returns the current time. If you did `x = now()`, the current time would be assigned to `x`, but if you did `x = now`, the function `now` itself would be assigned to `x`. `x` and `now` would both equally reference the function.

**Examples**
```py
# assigning new name

def foo():
    return 'bar'

def spam():
    return 'eggs'

baz = foo
baz() # returns 'bar'

ham = spam
ham() # returns 'eggs'
```
```py
# storing in container

import math
functions = [math.sqrt, math.factorial, math.log]
functions[0](25) # returns 5.0
# the above equivalent to math.sqrt(25)
```
```py
# passing as argument

class C:
    builtin_open = staticmethod(open)

# open function is passed
# to the staticmethod class
```
