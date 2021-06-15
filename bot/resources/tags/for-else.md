**for-else**

In Python it's possible to attach an `else` clause to a for loop. The code under the `else` block will be run if the `for` block is not broken out of, by either a `break`, `return`, or `raise` statement.

Here's an example of its usage:
```py
numbers = [1, 3, 5, 7, 8, 9, 11]

for number in numbers:
    if number % 2 == 0:
        print("Found an even number:", number)
        break
else:
    print("All numbers are odd. How odd.")
```
Try running this example but with an even number in the list, see how the output changes as you do so.
