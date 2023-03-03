---
embed:
    title: "The for-else block"
---
In Python it's possible to attach an `else` clause to a for loop. The code under the `else` block will be run when the iterable is exhausted (there are no more items to iterate over). Code within the else block will **not** run if the loop is broken out using `break`.

Here's an example of its usage:
```py
numbers = [1, 3, 5, 7, 9, 11]

for number in numbers:
    if number % 2 == 0:
        print(f"Found an even number: {number}")
        break
    print(f"{number} is odd.")
else:
    print("All numbers are odd. How odd.")
```
Try running this example but with an even number in the list, see how the output changes as you do so.
