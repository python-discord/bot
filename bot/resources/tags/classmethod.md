---
embed:
    title: "The `@classmethod` decorator"
---
Although most methods are tied to an _object instance_, it can sometimes be useful to create a method that does something with _the class itself_. To achieve this in Python, you can use the `@classmethod` decorator. This is often used to provide alternative constructors for a class.

For example, you may be writing a class that takes some magic token (like an API key) as a constructor argument, but you sometimes read this token from a configuration file. You could make use of a `@classmethod` to create an alternate constructor for when you want to read from the configuration file.
```py
class Bot:
    def __init__(self, token: str):
        self._token = token  

    @classmethod
    def from_config(cls, config: dict) -> Bot:
        token = config['token']
        return cls(token)

# now we can create the bot instance like this
alternative_bot = Bot.from_config(default_config)

# but this still works, too
regular_bot = Bot("tokenstring")
```
This is just one of the many use cases of `@classmethod`. A more in-depth explanation can be found [here](https://stackoverflow.com/questions/12179271/meaning-of-classmethod-and-staticmethod-for-beginner#12179752).
