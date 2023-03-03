---
aliases: ["fstrings", "fstring", "f-string"]
embed:
    title: "Format-strings"
---
Creating a Python string with your variables using the `+` operator can be difficult to write and read. F-strings (*format-strings*) make it easy to insert values into a string. If you put an `f` in front of the first quote, you can then put Python expressions between curly braces in the string.

```py
>>> snake = "pythons"
>>> number = 21
>>> f"There are {number * 2} {snake} on the plane."
"There are 42 pythons on the plane."
```
Note that even when you include an expression that isn't a string, like `number * 2`, Python will convert it to a string for you.
