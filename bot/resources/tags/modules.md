**modules**

In Python, a `module` is an extension that is `import`ed into another program, typically to either organize code.

**Example**

In our program, we want to organize our `add` and `minus` function into a `module` called `math.py`.

First, we would create our python file called `add_and_minus.py` and put the `add` and `minus` functions into it.

```py
# add_and_minus.py

def add(a, b):
    return a + b
def minus(a, b):
    return a - b
```
From here, we are able to `import` these functions into our `calculator.py` file.

```py
# calculator.py

import add_and_minus

first_number = add_and_minus.add(1, 2) # 3
second_number = add_and_minus.minus(first_number, 1) # 2
```
> *Note*
> 
> When importing modules, the python interpreter looks in both the local directory and `site-packages` for the `module`. If the module is *not found*, it raises a `ModuleNotFoundError`.
>
> See `!tags module-not-found` for more information about this exception.