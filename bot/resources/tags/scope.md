---
embed:
    title: "Scoping rules"
---
A *scope* defines the visibility of a name within a block, where a block is a piece of Python code executed as a unit. For simplicity, this would be a module, a function body, and a class definition. A name refers to text bound to an object.

*For more information about names, see `/tag names`*

A module is the source code file itself, and encompasses all blocks defined within it. Therefore if a variable is defined at the module level (top-level code block), it is a global variable and can be accessed anywhere in the module as long as the block in which it's referenced is executed after it was defined.

Alternatively if a variable is defined within a function block for example, it is a local variable. It is not accessible at the module level, as that would be *outside* its scope. This is the purpose of the `return` statement, as it hands an object back to the scope of its caller. Conversely if a function was defined *inside* the previously mentioned block, it *would* have access to that variable, because it is within the first function's scope.
```py
>>> def outer():
...     foo = 'bar'     # local variable to outer
...     def inner():
...         print(foo)  # has access to foo from scope of outer
...     return inner    # brings inner to scope of caller
...
>>> inner = outer()  # get inner function
>>> inner()  # prints variable foo without issue
bar
```
**Official Documentation**  
**1.** [Program structure, name binding and resolution](https://docs.python.org/3/reference/executionmodel.html#execution-model)  
**2.** [`global` statement](https://docs.python.org/3/reference/simple_stmts.html#the-global-statement)  
**3.** [`nonlocal` statement](https://docs.python.org/3/reference/simple_stmts.html#the-nonlocal-statement)
