A [`docstring`](https://docs.python.org/3/glossary.html#term-docstring) is a string with triple quotes that often used in file, classes, functions, etc. A docstring should have a clear explanation of exactly what the function does. You can also include descriptions of the function's parameter(s) and its return type, as shown below.
```py
def greet(name, age) -> str:
  """
  Return a string that greets the given person, including their name and age.

  :param name: The name to greet.
  :type name: str
  :param age: The age to display.
  :type age: int
  :return: String of the greeting.
  """
  return_string = f"Hello, {name} you are {age} years old!"
  return return_string
```
You can get the docstring by using `.__doc__` attribute. For the last example you can get it through: `print(greet.__doc__)`.

For more details about what docstring is and it's usage check out this guide by [Real Python](https://realpython.com/documenting-python-code/#docstrings-background), or the [PEP-257 docs](https://www.python.org/dev/peps/pep-0257/#what-is-a-docstring).
