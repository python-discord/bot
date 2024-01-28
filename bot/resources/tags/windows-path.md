---
embed:
    title: "PATH on Windows"
---
If you have installed Python but forgot to check the `Add Python to PATH` option during the installation, you may still be able to access your installation with ease.

If you did not uncheck the option to install the `py launcher`, then you'll instead have a `py` command which can be used in the same way. If you want to be able to access your Python installation via the `python` command, then your best option is to re-install Python (remembering to tick the `Add Python to PATH` checkbox).

You can pass any options to the Python interpreter, e.g. to install the [`numpy`](https://pypi.org/project/numpy/) module from PyPI you can run `py -3 -m pip install numpy` or `python -m pip install numpy`.

You can also access different versions of Python using the version flag of the `py` command, like so:
```
C:\Users\Username> py -3.7
... Python 3.7 starts ...
C:\Users\Username> py -3.6
... Python 3.6 starts ...
C:\Users\Username> py -2
... Python 2 (any version installed) starts ...
```
