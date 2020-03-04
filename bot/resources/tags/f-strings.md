In Python, there are several ways to do string interpolation, including using `%s`\'s and by using the `+` operator to concatenate strings together. However, because some of these methods offer poor readability and require typecasting to prevent errors, you should for the most part be using a feature called format strings.

**In Python 3.6 or later, we can use f-strings like this:**
```py
snake = "Pythons"
print(f"{snake} are some of the largest snakes in the world")
```
**In earlier versions of Python or in projects where backwards compatibility is very important, use  str.format() like this:**
```py
snake = "Pythons"

# With str.format() you can either use indexes
print("{0} are some of the largest snakes in the world".format(snake))

# Or keyword arguments
print("{family} are some of the largest snakes in the world".format(family=snake))
```
