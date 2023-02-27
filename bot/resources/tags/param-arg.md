---
embed:
    title: "Parameters vs. arguments"
---
A parameter is a variable defined in a function signature (the line with `def` in it), while arguments are objects passed to a function call.

```py
def square(n): # n is the parameter
    return n*n

print(square(5)) # 5 is the argument
```

Note that `5` is the argument passed to `square`, but `square(5)` in its entirety is the argument passed to `print`
