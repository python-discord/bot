---
embed:
    title: "Dictionary comprehensions"
---
Dictionary comprehensions (*dict comps*) provide a convenient way to make dictionaries, just like list comps:
```py
>>> {word.lower(): len(word) for word in ('I', 'love', 'Python')}
{'i': 1, 'love': 4, 'python': 6}
```
The syntax is very similar to list comps except that you surround it with curly braces and have two expressions: one for the key and one for the value.

One can use a dict comp to change an existing dictionary using its `items` method
```py
>>> first_dict = {'i': 1, 'love': 4, 'python': 6}
>>> {key.upper(): value * 2 for key, value in first_dict.items()}
{'I': 2, 'LOVE': 8, 'PYTHON': 12}
```
For more information and examples, check out [PEP 274](https://peps.python.org/pep-0274/)
