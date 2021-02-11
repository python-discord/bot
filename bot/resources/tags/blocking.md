**What is asynchronous programming?**

An asynchronous program doesn't wait for step to be finished before executing another one, but just keeps continuing executing other steps. It will also know what to do when the previous step finishes executing. It is faster than synchronous programming for this reason.

Consider this example from [Miguel Grinberg’s 2017 PyCon talk](https://www.youtube.com/watch?t=4m29s&v=iG6fr81xHKA&feature=youtu.be), about playing multiple games of chess at once.


**What does blocking mean?**

In asynchronous programming, blocking calls are all the parts of your function that are not using `await`. Not all forms of blocking are bad, and using blocking calls are inevitable, but make sure not to use too much, or else the program will freeze and you cannot do other tasks until that task is done, incrasing the amount of time it takes for the progrsam to complete.


**How can I find asynchronous modules?**

Most Python modules have an asynchronous implementation. For example, [`sqlite3`](https://docs.python.org/3/library/sqlite3.html) has [`aiosqlite`](https://pypi.org/project/aiosqlite/), and [`praw`](https://pypi.org/project/praw/) has [`asycpraw`](https://pypi.org/project/asyncpraw/). You try searching on [PyPi](https://pypi.org), or check out [this curated list of Python asyncio frameworks](https://github.com/timofurrer/awesome-asyncio).
You can also ask in <#630504881542791169> for options.

**Resources for Further Reading**

[Getting Started With Async Features in Python – Real Python](https://realpython.com/python-async-features/)
[Async IO in Python: A Complete Walkthrough - Real Python](https://realpython.com/async-io-python/)
