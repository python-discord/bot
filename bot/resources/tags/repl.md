**Read-Eval-Print Loop**

A REPL is an interactive language shell environment. It first **reads** one or more expressions entered by the user, **evaluates** it, yields the result, and **prints** it out to the user. It will then **loop** back to the **read** step.

To use python's REPL, execute the interpreter with no arguments. This will drop you into the interactive interpreter shell, print out some relevant information, and then prompt you with the primary prompt `>>>`. At this point it is waiting for your input.

Firstly you can start typing in some valid python expressions, pressing <return> to either bring you to the **eval** step, or prompting you with the secondary prompt `...` (or no prompt at all depending on your environment), meaning your expression isn't yet terminated and it's waiting for more input. This is useful for code that requires multiple lines like loops, functions, and classes. If you reach the secondary prompt in a clause that can have an arbitrary amount of expressions, you can terminate it by pressing <return> on a blank line. In other words, for the last expression you write in the clause, <return> must be pressed twice in a row.

Alternatively, you can make use of the builtin `help()` function. `help(thing)` to get help on some `thing` object, or `help()` to start an interactive help session. This mode is extremely powerful, read the instructions when first entering the session to learn how to use it.

Lastly you can run your code with the `-i` flag to execute your code normally, but be dropped into the REPL once execution is finished, giving you access to all your global variables/functions in the REPL.

To **exit** either a help session, or normal REPL prompt, you must send an EOF signal to the prompt. In *nix systems, this is done with `ctrl + D`, and in windows systems it is `ctrl + Z`. You can also exit the normal REPL prompt with the dedicated functions `exit()` or `quit()`.
