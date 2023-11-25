---
embed:
    title: "Docstrings"
---
A [`docstring`](https://docs.python.org/3/glossary.html#term-docstring) is a string - always using triple quotes - that's placed at the top of files, classes and functions. A docstring should contain a clear explanation of what it's describing. You can also include descriptions of the subject's parameter(s) and what it returns, as shown below:
```py
def greet(name: str, age: int) -> str:
    """
    Return a string that greets the given person, using their name and age.

    :param name: The name of the person to greet.
    :param age: The age of the person to greet.

    :return: The greeting.
    """
    return f"Hello {name}, you are {age} years old!"
```
You can get the docstring by using the [`inspect.getdoc`](https://docs.python.org/3/library/inspect.html#inspect.getdoc) function, from the built-in [`inspect`](https://docs.python.org/3/library/inspect.html) module, or by accessing the `.__doc__` attribute. `inspect.getdoc` is often preferred, as it clears indents from the docstring.

For the last example, you can print it by doing this: `print(inspect.getdoc(greet))`.

For more details about what a docstring is and its usage, check out this guide by [Real Python](https://realpython.com/documenting-python-code/#docstrings-background), or the [official docstring specification](https://peps.python.org/pep-0257/#what-is-a-docstring).
