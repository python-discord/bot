A [`docstring`](https://docs.python.org/3/glossary.html#term-docstring) is a string with triple quotes that's placed at the top of files, classes and functions. A docstring should contain a clear explanation of what it's describing. You can also include descriptions of the subject's parameter(s) and its return type, as shown below:
```py
def greet(name: str, age: int) -> str:
    """
    Return a string that greets the given person, including their name and age.

    :param name: The name to greet.
    :param age: The age to display.

    :return: String representation of the greeting.
    """
    return f"Hello {name}, you are {age} years old!"
```
You can get the docstring by using the `.__doc__` attribute. For the last example, you can print it by doing this: `print(greet.__doc__)`.

For more details about what a docstring is and its usage, check out this guide by [Real Python](https://realpython.com/documenting-python-code/#docstrings-background), or the [PEP-257 docs](https://www.python.org/dev/peps/pep-0257/#what-is-a-docstring).
