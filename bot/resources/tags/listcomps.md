Do you ever find yourself writing something like:
```py
even_numbers = []
for n in range(20):
    if n % 2 == 0:
        even_numbers.append(n)
```
Using list comprehensions can simplify this significantly, and greatly improve code readability. If we rewrite the example above to use list comprehensions, it would look like this:
```py
even_numbers = [n for n in range(20) if n % 2 == 0]
```
This also works for generators, dicts and sets by using `()` or `{}` instead of `[]`.

For more info, see [this pythonforbeginners.com post](http://www.pythonforbeginners.com/basics/list-comprehensions-in-python) or [PEP 202](https://www.python.org/dev/peps/pep-0202/).
