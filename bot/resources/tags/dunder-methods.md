Double-underscore methods, or "dunder" methods, are special methods defined in a class that are invoked implicitly. Like the name suggests, they are prefixed and suffixed with dunders. You've probably already seen some, such as the `__init__` dunder method, also known as the "constructor" of a class, which is implicitly invoked when you instantiate an instance of a class.

When you create a new class, all the default dunder methods are inherited from its superclass (which is `object` if no superclass is specified). However, we can override them by redefining the methods within this new class. For example, the default `__init__` method from `object` doesn't take any arguments, so we almost always override that to fit our needs.

Other common dunder methods to override are `__str__` and `__repr__`. `__str__` is the user-friendly string representation of an object, and is implicitly called on arguments passed into the `str` function. `__repr__` is the developer-friendly string representation of an object - usually the syntax to recreate it - and is called by the `repr` function.

```py
class Foo:
    def __init__(self, value):  # constructor
        self.value = value
    def __str__(self):
        return f"This is a Foo object, with a value of {self.value}!"  # string representation
    def __repr__(self):
        return f"Foo({self.value})"  # way to recreate this object


bar = Foo(5)

print(bar)  # print also implicitly calls __str__
# Output: This is a Foo object, with a value of 5!

print(repr(bar))  # dev-friendly representation
# Output: Foo(5)
```

Another example: did you know that when you use the `<left operand> + <right operand>` syntax, you're implicitly calling `<left operand>.__add__(<right operand>)`? The same applies to other operators!
