---
embed:
    title: "Decorators"
---
A decorator is a function that modifies another function.

Consider the following example of a timer decorator:
```py
>>> import time
>>> def timer(f):
...     def inner(*args, **kwargs):
...         start = time.time()
...         result = f(*args, **kwargs)
...         print('Time elapsed:', time.time() - start)
...         return result
...     return inner
...
>>> @timer
... def slow(delay=1):
...     time.sleep(delay)
...     return 'Finished!'
...
>>> print(slow())
Time elapsed: 1.0011568069458008
Finished!
>>> print(slow(3))
Time elapsed: 3.000307321548462
Finished!
```

More information:  
- [Corey Schafer's video on decorators](https://youtu.be/FsAPt_9Bf3U)  
- [Real python article](https://realpython.com/primer-on-python-decorators/)  
