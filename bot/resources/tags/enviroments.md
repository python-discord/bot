**Python Enviroments**

The main purpose of Python [virtual environments](https://docs.python.org/3/library/venv.html#venv-def) is to create an isolated environment for Python projects. This means that each project can have its own dependencies, such as third party packages installed using `pip`, regardless of what dependencies every other project has.

To see the current enviroment in use by python you can run:
```py
>>> import sys
>>> print(sys.executable)
/usr/bin/python3
```

To see the enviroment in use by `pip` you can do `pip debug`, or `pip3 debug` for linux/macOS. The 3rd line of the output will contain the path in use. I.E. `sys.executable: /usr/bin/python3`

If the python's `sys.executable` doesn't match pip's then they are currently using different enviroments! This may cause python to raise a `ModuleNotFoundError` when you try to use a package you just installed with pip, as it was installed to a different enviroment.

Further reading:  
• [Real Python's primer on Python Virtual Environments](https://realpython.com/python-virtual-environments-a-primer)  
• [pyenv: Simple Python Version Management](https://github.com/pyenv/pyenv)
