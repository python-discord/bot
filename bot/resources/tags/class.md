---
embed:
    title: "Classes"
---
Classes are used to create objects that have specific behavior.

Every object in Python has a class, including `list`s, `dict`ionaries and even numbers. Using a class to group code and data like this is the foundation of Object Oriented Programming. Classes allow you to expose a simple, consistent interface while hiding the more complicated details. This simplifies the rest of your program and makes it easier to separately maintain and debug each component.

Here is an example class:

```python
class Foo:
    def __init__(self, somedata):
        self.my_attrib = somedata

    def show(self):
        print(self.my_attrib)
```

To use a class, you need to instantiate it. The following creates a new object named `bar`, with `Foo` as its class.

```python
bar = Foo('data')
bar.show()
```

We can access any of `Foo`'s methods via `bar.my_method()`, and access any of `bar`s data via `bar.my_attribute`.
