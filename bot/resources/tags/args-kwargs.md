---
embed:
    title: "The `*args` and `**kwargs` parameters"
---
These special parameters allow functions to take arbitrary amounts of positional and keyword arguments. The names `args` and `kwargs` are purely convention, and could be named any other valid variable name. The special functionality comes from the single and double asterisks (`*`). If both are used in a function signature, `*args` **must** appear before `**kwargs`.

**Single asterisk**
`*args` will ingest an arbitrary amount of **positional arguments**, and store it in a tuple. If there are parameters after `*args` in the parameter list with no default value, they will become **required** keyword arguments by default.

**Double asterisk**
`**kwargs` will ingest an arbitrary amount of **keyword arguments**, and store it in a dictionary. There can be **no** additional parameters **after** `**kwargs` in the parameter list.

**Use cases**  
- **Decorators** (see `/tag decorators`)  
- **Inheritance** (overriding methods)  
- **Future proofing** (in the case of the first two bullet points, if the parameters change, your code won't break)  
- **Flexibility** (writing functions that behave like `dict()` or `print()`)  

*See* `/tag positional-keyword` *for information about positional and keyword arguments*
