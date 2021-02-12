**What is asynchronous programming?**

An asynchronous program doesn't wait for step to be finished before executing another one, but just keeps continuing executing other steps.

It will also know what to do when the previous step finishes executing.

Consider this example from [Miguel Grinberg’s 2017 PyCon talk](https://www.youtube.com/watch?t=4m29s&v=iG6fr81xHKA&feature=youtu.be), about playing multiple games of chess at once.


**What does blocking mean?**

In asynchronous programming, blocking calls are all the parts of your function that are not using `await`.

Not all forms of blocking are bad, and using blocking calls are inevitable, but make sure not to use too much.

This is because the program will freeze and you cannot do other tasks until that task is done, increasing the amount of time it takes for the progrsam to complete.

**Resources for Further Reading**

[Getting Started With Async Features in Python – Real Python](https://realpython.com/python-async-features/)

[Async IO in Python: A Complete Walkthrough - Real Python](https://realpython.com/async-io-python/)
