A [`docstring`](https://docs.python.org/3/glossary.html#term-docstring) is a string with triple quotes that often used in file, classes, functions, etc. Docstrings usually has clear explanation, parameter(s) and return type.

Here's an example of usage of a docstring:
```py
def greet(name, age) -> str:
  """
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
