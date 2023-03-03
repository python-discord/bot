---
embed:
    title: "Indentation"
---
Indentation is leading whitespace (spaces and tabs) at the beginning of a line of code. In the case of Python, they are used to determine the grouping of statements.

Spaces should be preferred over tabs. To be clear, this is in reference to the character itself, not the keys on a keyboard. Your editor/IDE should be configured to insert spaces when the TAB key is pressed. The amount of spaces should be a multiple of 4, except optionally in the case of continuation lines.

**Example**
```py
def foo():
    bar = 'baz'  # indented one level
    if bar == 'baz':
        print('ham')  # indented two levels
    return bar  # indented one level
```
The first line is not indented. The next two lines are indented to be inside of the function definition. They will only run when the function is called. The fourth line is indented to be inside the `if` statement, and will only run if the `if` statement evaluates to `True`. The fifth and last line is like the 2nd and 3rd and will always run when the function is called. It effectively closes the `if` statement above as no more lines can be inside the `if` statement below that line.

**Indentation is used after:**
**1.** [Compound statements](https://docs.python.org/3/reference/compound_stmts.html) (eg. `if`, `while`, `for`, `try`, `with`, `def`, `class`, and their counterparts)
**2.** [Continuation lines](https://peps.python.org/pep-0008/#indentation)

**More Info**
**1.** [Indentation style guide](https://peps.python.org/pep-0008/#indentation)
**2.** [Tabs or Spaces?](https://peps.python.org/pep-0008/#tabs-or-spaces)
**3.** [Official docs on indentation](https://docs.python.org/3/reference/lexical_analysis.html#indentation)
