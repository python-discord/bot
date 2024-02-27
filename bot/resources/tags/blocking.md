---
embed:
    title: "Asynchronous programming"
---
Imagine that you're coding a Discord bot and every time somebody uses a command, you need to get some information from a database. But there's a catch: the database servers are acting up today and take a whole 10 seconds to respond. If you do **not** use asynchronous methods, your whole bot will stop running until it gets a response from the database. How do you fix this? Asynchronous programming.

**What is asynchronous programming?**
An asynchronous program utilises the `async` and `await` keywords. An asynchronous program pauses what it's doing and does something else whilst it waits for some third-party service to complete whatever it's supposed to do. Any code within an `async` context manager or function marked with the `await` keyword indicates to Python, that whilst this operation is being completed, it can do something else. For example:

```py
import discord

# Bunch of bot code

async def ping(ctx):
    await ctx.send("Pong!")
```
**What does the term "blocking" mean?**
A blocking operation is wherever you do something without `await`ing it. This tells Python that this step must be completed before it can do anything else. Common examples of blocking operations, as simple as they may seem, include: outputting text, adding two numbers and appending an item onto a list. Most common Python libraries have an asynchronous version available to use in asynchronous contexts.

**`async` libraries**
- The standard async library - `asyncio`
- Asynchronous web requests - `aiohttp`
- Talking to PostgreSQL asynchronously - `asyncpg`
- MongoDB interactions asynchronously - `motor`
- Check out [this](https://github.com/timofurrer/awesome-asyncio) list for even more!
