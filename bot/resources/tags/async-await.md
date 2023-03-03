---
embed:
    title: "Concurrency in Python"
---
Python provides the ability to run multiple tasks and coroutines simultaneously with the use of the `asyncio` library, which is included in the Python standard library.

This works by running these coroutines in an event loop, where the context of the running coroutine switches periodically to allow all other coroutines to run, thus giving the appearance of running at the same time. This is different to using threads or processes in that all code runs in the main process and thread, although it is possible to run coroutines in other threads.

To call an async function we can either `await` it, or run it in an event loop which we get from `asyncio`.

To create a coroutine that can be used with asyncio we need to define a function using the `async` keyword:
```py
async def main():
    await something_awaitable()
```
Which means we can call `await something_awaitable()` directly from within the function. If this were a non-async function, it would raise the exception `SyntaxError: 'await' outside async function`

To run the top level async function from outside the event loop we need to use [`asyncio.run()`](https://docs.python.org/3/library/asyncio-task.html#asyncio.run), like this:
```py
import asyncio

async def main():
    await something_awaitable()

asyncio.run(main())
```
Note that in the `asyncio.run()`, where we appear to be calling `main()`, this does not execute the code in `main`. Rather, it creates and returns a new `coroutine` object (i.e `main() is not main()`) which is then handled and run by the event loop via `asyncio.run()`.

To learn more about asyncio and its use, see the [asyncio documentation](https://docs.python.org/3/library/asyncio.html).
