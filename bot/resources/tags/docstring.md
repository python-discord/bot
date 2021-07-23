A [`docstring`](https://docs.python.org/3/glossary.html#term-docstring) is a string with triple quotes that often used in file, classes, functions, etc. A docstring usually has clear explanation (such as what the function do, purposes of the function, and other details of the function), parameter(s) and a return type.

Here's an example of a docstring:
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
