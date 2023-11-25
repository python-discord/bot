---
embed:
    title: "`if __name__ == '__main__'`"
---
This is a statement that is only true if the module (your source code) it appears in is being run directly, as opposed to being imported into another module.  When you run your module, the `__name__` special variable is automatically set to the string `'__main__'`. Conversely, when you import that same module into a different one, and run that, `__name__` is instead set to the filename of your module minus the `.py` extension.

**Example**
```py
# foo.py

print('spam')

if __name__ == '__main__':
    print('eggs')
```
If you run the above module `foo.py` directly, both `'spam'`and `'eggs'` will be printed. Now consider this next example:
```py
# bar.py

import foo
```
If you run this module named `bar.py`, it will execute the code in `foo.py`. First it will print `'spam'`, and then the `if` statement will fail, because `__name__` will now be the string `'foo'`.

**Why would I do this?**

- Your module is a library, but also has a special case where it can be run directly
- Your module is a library and you want to safeguard it against people running it directly (like what `pip` does)
- Your module is the main program, but has unit tests and the testing framework works by importing your module, and you want to avoid having your main code run during the test
