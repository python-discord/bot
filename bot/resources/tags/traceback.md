Please provide the full traceback for your exception in order to help us identify your issue.

A full traceback could look like:
```py
Traceback (most recent call last):
    File "tiny", line 3, in
        do_something()
    File "tiny", line 2, in do_something
        a = 6 / b
ZeroDivisionError: integer division or modulo by zero
```
The best way to read your traceback is bottom to top.

• Identify the exception raised (e.g. `ZeroDivisionError`)  
• Make note of the line number (in this case 2), and navigate there in your program.  
• Try to understand why the error occurred (in this case because `b` must be `0`).

To read more about exceptions and errors, please refer to the [PyDis Wiki](https://pythondiscord.com/pages/guides/pydis-guides/asking-good-questions/#examining-tracebacks) or the [official Python tutorial](https://docs.python.org/3.7/tutorial/errors.html).
