---
embed:
    title: "Read-Eval-Print Loop (REPL)"
---
A REPL is an interactive shell where you can execute individual lines of code one at a time, like so:
```python-repl
>>> x = 5
>>> x + 2
7
>>> for i in range(3):
...     print(i)
...
0
1
2
>>>
```
To enter the REPL, run `python` (`py` on Windows) in the command line without any arguments. The `>>>` or `...` at the start of some lines are prompts to enter code, and indicate that you are in the Python REPL. Any other lines show the output of the code.

Trying to execute commands for the command-line (such as `pip install xyz`) in the REPL will throw an error. To run these commands, exit the REPL first by running `exit()` and then run the original command.
