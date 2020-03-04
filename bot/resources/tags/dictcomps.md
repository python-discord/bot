**Dictionary Comprehensions**

Like lists, there is a convenient way of creating dictionaries:
```py
>>> ftoc = {f: round((5/9)*(f-32)) for f in range(-40,101,20)}
>>> print(ftoc)
{-40: -40, -20: -29, 0: -18, 20: -7, 40: 4, 60: 16, 80: 27, 100: 38}
```
In the example above, I created a dictionary of temperatures in Fahrenheit, that are mapped to (*roughly*) their Celsius counterpart within a small range. These comprehensions are useful for succinctly creating dictionaries from some other sequence.

They are also very useful for inverting the key value pairs of a dictionary that already exists, such that the value in the old dictionary is now the key, and the corresponding key is now its value:
```py
>>> ctof = {v:k for k, v in ftoc.items()}
>>> print(ctof)
{-40: -40, -29: -20, -18: 0, -7: 20, 4: 40, 16: 60, 27: 80, 38: 100}
```

Also like list comprehensions, you can add a conditional to it in order to filter out items you don't want.

For more information and examples, check [PEP 274](https://www.python.org/dev/peps/pep-0274/)
