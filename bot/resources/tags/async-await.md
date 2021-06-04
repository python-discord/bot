**Concurrency in Python**

Python provides the ability to run multiple tasks and coroutines simultaneously with the use of the `asyncio` library, which is included in the Python standard library.

This works by running these coroutines in an event loop, where the context of which coroutine is being run is switches periodically to allow all of them to run, giving the appearance of running at the same time. This is different to using threads or processes in that all code is run in the main process and thread, although it is possible to run coroutines in threads.

To call an async function we can either `await` it, or run it in an event loop which we get from `asyncio`.

To create a coroutine that can be used with asyncio we need to define a function using the async keyword:
```py
async def main():
    await something_awaitable()
```
Which means we can call `await something_awaitable()` directly from within the function. If this were a non-async function this would have raised an exception like: `SyntaxError: 'await' outside async function`

To run the top level async function from outside of the event loop we can get an event loop from `asyncio`, and then use that loop to run the function:
```py
from asyncio import get_event_loop

async def main():
    await something_awaitable()

loop = get_event_loop()
loop.run_until_complete(main())
```
Note that in the `run_until_complete()` where we appear to be calling `main()`, this does not execute the code in `main`, rather it returns a `coroutine` object which is then handled and run by the event loop via `run_until_complete()`.

To learn more about asyncio and its use, see the [asyncio documentation](https://docs.python.org/3/library/asyncio.html).
