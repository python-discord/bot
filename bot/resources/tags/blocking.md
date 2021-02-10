**What does blocking mean?**
In asynchronous programming, blocking calls are all the parts of your function that are not using `await`. Not all forms of blocking are bad, and using blocking calls are inevitable, but make sure not to use too much, or else the program will freeze and you cannot do other tasks.

**Examples of Blocking**
A major example of blocking is using `time.sleep()`. Use `asyncio.sleep()` instead.
Example:
```py
# bad
time.sleep(10)
# good
await asyncio.sleep(10)
```
Another example is using the `requests` library. It's good for non-asynchronous programming, but certain requests can block the event too long with `asyncio`. Instead use `aiohttp`. Example:
```py
# bad
r = requests.get('http://aws.random.cat/meow')
if r.status_code == 200:
    js = r.json()
    await channel.send(js['file'])
# good
async with aiohttp.ClientSession() as session:
    async with session.get('http://aws.random.cat/meow') as r:
        if r.status == 200:
            js = await r.json()
            await channel.send(js['file'])
```

**How can I find asynchronous modules?**
Most Python modules have an asynchronous implementation. For example, `sqlite3` has `aiosqlite`, and `praw` has `asycpraw`. You try searching on [PyPi](https://pypi.org), or check out [this curated list of Python asyncio frameworks](https://github.com/timofurrer/awesome-asyncio).
You can also ask here in this server for options.

**Resources for Further Reading**
[Discord.py Frequently Asked Questions: What does 'blocking' mean?](https://discordpy.readthedocs.io/en/latest/faq.html#what-does-blocking-mean)
