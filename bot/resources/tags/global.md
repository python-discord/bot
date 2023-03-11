---
embed:
    title: "Globals"
---
When adding functions or classes to a program, it can be tempting to reference inaccessible variables by declaring them as global. Doing this can result in code that is harder to read, debug and test. Instead of using globals, pass variables or objects as parameters and receive return values.

Instead of writing
```py
def update_score():
    global score, roll
    score = score + roll
update_score()
```
do this instead
```py
def update_score(score, roll):
    return score + roll
score = update_score(score, roll)
```
For in-depth explanations on why global variables are bad news in a variety of situations, see [this Stack Overflow answer](https://stackoverflow.com/questions/19158339/why-are-global-variables-evil/19158418#19158418).
