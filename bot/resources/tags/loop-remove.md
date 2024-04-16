---
embed:
    title: "Removing items inside a for loop"
---
Avoid removing items from a collection, such as a list, as you iterate that collection in a `for` loop:
```py
data = [1, 2, 3, 4]
for item in data:
    data.remove(item)
print(data)  # [2, 4] <-- every OTHER item was removed!
```
`for` loops track the index of the current item with a kind of pointer. Removing an element causes all other elements to shift, but the pointer is not changed:
```py
# Start the loop:
[1, 2, 3, 4] # First iteration: point to the first element
 ^
[2, 3, 4]    # Remove current: all elements shift
 ^
[2, 3, 4]    # Next iteration: move the pointer
    ^
[2, 4]       # Remove current: all elements shift
    ^
# Done
```
You can avoid this pitfall by:
- using a list comprehension to produce a new list (as a way of filtering items):
  ```py
  data = [x for x in data if x % 2 == 0]
  ```
- using a `while` loop and `.pop()` (treating the list as a stack):
  ```py
  while data:
      item = data.pop()
  ```
- consider: you may not need to remove items in the first place!
