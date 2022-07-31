**multiple-python**

If you are experiencing `ModuleNotFoundError` errors, but you have installed the `library` with `pip`, then you have multiple python interpreters installed.

**Example**
Often, you may have a `python2` *and* a `python3` installed. In this case, the libraries installed may not go to the desired location. You can either install modules with the following syntax to ensure that the *right* python `pip` installs it.

```
python -m pip install <library>
```
Where `python` is the correct python version. This installs the library to that `python`'s location.

<br>

**Or, you can remove all other python versions except for the one that you want.** 

This ensures that only one python `pip` will manage


