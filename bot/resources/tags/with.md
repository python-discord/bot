---
embed:
    title: "The `with` keyword"
---
The `with` keyword triggers a context manager. Context managers automatically set up and take down data connections, or any other kind of object that implements the magic methods `__enter__` and `__exit__`.
```py
with open("test.txt", "r") as file:
    do_things(file)
```
The above code automatically closes `file` when the `with` block exits, so you never have to manually do a `file.close()`. Most connection types, including file readers and database connections, support this.

For more information, read [the official docs](https://docs.python.org/3/reference/compound_stmts.html#with), watch [Corey Schafer\'s context manager video](https://www.youtube.com/watch?v=-aKFBoZpiqA), or see [PEP 343](https://peps.python.org/pep-0343/).
