---
embed:
    title: "Dunder methods"
---
Double-underscore methods, or "dunder" methods, are special methods defined in a class that are invoked implicitly. Like the name suggests, they are prefixed and suffixed with dunders. You've probably already seen some, such as the `__init__` dunder method, also known as the "constructor" of a class, which is implicitly invoked when you instantiate an instance of a class.

When you create a new class, there will be default dunder methods inherited from the `object` class. However, we can override them by redefining these methods within the new class. For example, the default `__init__` method from `object` doesn't take any arguments, so we almost always override that to fit our needs.

Other common dunder methods to override are `__str__` and `__repr__`. `__repr__` is the developer-friendly string representation of an object - usually the syntax to recreate it - and is implicitly called on arguments passed into the `repr` function. `__str__` is the user-friendly string representation of an object, and is called by the `str` function. Note here that, if not overriden, the default `__str__` invokes `__repr__` as a fallback.

```py
class Foo:
    def __init__(self, value):  # constructor
        self.value = value
    def __str__(self):
        return f"This is a Foo object, with a value of {self.value}!"  # string representation
    def __repr__(self):
        return f"Foo({self.value!r})"  # way to recreate this object


bar = Foo(5)

# print also implicitly calls __str__
print(bar)  # Output: This is a Foo object, with a value of 5!

# dev-friendly representation
print(repr(bar))  # Output: Foo(5)
```

Another example: did you know that when you use the `<left operand> + <right operand>` syntax, you're implicitly calling `<left operand>.__add__(<right operand>)`? The same applies to other operators, and you can look at the [`operator` built-in module documentation](https://docs.python.org/3/library/operator.html) for more information!
