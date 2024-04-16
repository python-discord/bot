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
While iterating with a for loop, an index tracks the current position in the list. If the list is modified, this index may no longer refer to the same element, causing elements to be repeated or skipped.
```py
[1, 2, 3, 4] # First iteration: point to the first element
 ^
[2, 3, 4]    # Remove current: all elements shift
 ^
[2, 3, 4]    # Next iteration: move the pointer
    ^        # and so on...
```
You can avoid this pitfall by:
- using a **list comprehension** to produce a new list (as a way of filtering items):
  ```py
  data = [x for x in data if x % 2 == 0]
  ```
- using a `while` loop and `.pop()` (treating the list as a stack):
  ```py
  while data:
      item = data.pop()
  ```
- considering whether you need to remove items in the first place!
