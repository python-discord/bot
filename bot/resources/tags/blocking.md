**Why do we need asynchronous programming?**

Imagine that you're coding a Discord bot and every time somebody uses a command, you need to get some information from a database. But there's a catch: the database servers are acting up today and take a whole 10 seconds to respond. If you did **not** use asynchronous methods, your whole bot will stop running until it gets a response from the database. How do you fix this? Asynchronous programming.

**What is asynchronous programming?**

An asynchronous program utilises the `async` and `await` keywords. An asynchronous program pauses what it's doing and does something else whilst it waits for some third-party service to complete whatever it's supposed to do.
