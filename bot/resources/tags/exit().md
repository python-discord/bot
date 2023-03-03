---
embed:
    title: "Exiting programmatically"
---
If you want to exit your code programmatically, you might think to use the functions `exit()` or `quit()`, however this is bad practice. These functions are constants added by the [`site`](https://docs.python.org/3/library/site.html#module-site) module as a convenient method for exiting the interactive interpreter shell, and should not be used in programs.

You should use either [`SystemExit`](https://docs.python.org/3/library/exceptions.html#SystemExit) or [`sys.exit()`](https://docs.python.org/3/library/sys.html#sys.exit) instead.
There's not much practical difference between these two other than having to `import sys` for the latter. Both take an optional argument to provide an exit status.

[Official documentation](https://docs.python.org/3/library/constants.html#exit) with the warning not to use `exit()` or `quit()` in source code.
