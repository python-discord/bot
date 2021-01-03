**PATH on Windows**

If you have installed Python but you forgot to check the *Add Python to PATH* option during the installation you may still be able to access your installation with ease.

If you did not uncheck the option to install the Python launcher then you will find a `py` command on your system. If you want to be able to open your Python installation by running `python` then your best option is to re-install Python.

Otherwise, you can access your install using the `py` command in Command Prompt. Where you may type something with the `python` command like:
```
C:\Users\Username> python3 my_application_file.py
```

You can achieve the same result using the `py` command like this:
```
C:\Users\Username> py -3 my_application_file.py
```

You can pass any options to the Python interpreter after you specify a version, for example, to install a Python module using `pip` you can run:
```
C:\Users\Username> py -3 -m pip install numpy
```

You can also access different versions of Python using the version flag, like so:
```
C:\Users\Username> py -3.7
... Python 3.7 starts ...
C:\Users\Username> py -3.6
... Python 3.6 stars ...
C:\Users\Username> py -2
... Python 2 (any version installed) starts ...
```
