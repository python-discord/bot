---
aliases: ["envs"]
embed:
    title: "Python environments"
---
The main purpose of Python [virtual environments](https://docs.Python.org/3/library/venv.html#venv-def) is to create an isolated environment for Python projects. This means that each project can have its own dependencies, such as third party packages installed using pip, regardless of what dependencies every other project has.

To see the current environment in use by Python, you can run:
```py
>>> import sys
>>> sys.executable
'/usr/bin/python3'
```

To see the environment in use by pip, you can do `pip debug` (`pip3 debug` for Linux/macOS). The 3rd line of the output will contain the path in use e.g. `sys.executable: /usr/bin/python3`.

If Python's `sys.executable` doesn't match pip's, then they are currently using different environments! This may cause Python to raise a `ModuleNotFoundError` when you try to use a package you just installed with pip, as it was installed to a different environment.

**Why use a virtual environment?**

- Resolve dependency issues by allowing the use of different versions of a package for different projects. For example, you could use Package A v2.7 for Project X and Package A v1.3 for Project Y.  
- Make your project self-contained and reproducible by capturing all package dependencies in a requirements file. Try running `pip freeze` to see what you currently have installed!  
- Keep your global `site-packages/` directory tidy by removing the need to install packages system-wide which you might only need for one project.


**Further reading:**

- [Python Virtual Environments: A Primer](https://realpython.com/python-virtual-environments-a-primer)  
- [pyenv: Simple Python Version Management](https://github.com/pyenv/pyenv)
