**Joining Iterables**

Suppose you want to nicely display a list (or some other iterable). The naive solution would be something like this.
```py
colors = ['red', 'green', 'blue', 'yellow']
output = ""
separator = ", "
for color in colors:
    output += color + separator
print(output) # Prints 'red, green, blue, yellow, '
```
However, this solution is flawed. The separator is still added to the last color, and it is slow.

The better way is to use `str.join`.
```py
colors = ['red', 'green', 'blue', 'yellow']
separator = ", "
print(separator.join(colors)) # Prints 'red, green, blue, yellow'
```
This method is much simpler, faster, and solves the problem of the extra separator. An important thing to note is that you can only `str.join` strings. For a list of ints, 
you must convert each element to a string before joining.
```py
integers = [1, 3, 6, 10, 15]
print(", ".join(str(e) for e in integers)) # Prints '1, 3, 6, 10, 15'
```
