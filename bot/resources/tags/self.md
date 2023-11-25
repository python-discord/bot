---
embed:
    title: "Class instance"
---
When calling a method from a class instance (ie. `instance.method()`), the instance itself will automatically be passed as the first argument implicitly. By convention, we call this `self`, but it could technically be called any valid variable name.

```py
class Foo:
    def bar(self):
        print('bar')

    def spam(self, eggs):
        print(eggs)

foo = Foo()
```

If we call `foo.bar()`, it is equivalent to doing `Foo.bar(foo)`. Our instance `foo` is passed for us to the `bar` function, so while we initially gave zero arguments, it is actually called with one.

Similarly if we call `foo.spam('ham')`, it is equivalent to
doing `Foo.spam(foo, 'ham')`.

**Why is this useful?**

Methods do not inherently have access to attributes defined in the class. In order for any one method to be able to access other methods or variables defined in the class, it must have access to the instance.

Consider if outside the class, we tried to do this: `spam(foo, 'ham')`. This would give an error, because we don't have access to the `spam` method directly, we have to call it by doing `foo.spam('ham')`. This is also the case inside of the class. If we wanted to call the `bar` method inside the `spam` method, we'd have to do `self.bar()`, just doing `bar()` would give an error.
