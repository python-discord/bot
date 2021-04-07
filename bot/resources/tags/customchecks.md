**Custom Command Checks in discord.py**

You may find yourself in need of a check decorator to do something that doesn't exist in discord.py by default, but fear not, you can make your own! Using discord.py you can use `discord.ext.commands.check` to create you own checks like this:
```py
from discord.ext.commands import check, Context

def in_any_channel(*channels):
  async def predicate(ctx: Context):
    return ctx.channel.id in channels
  return check(predicate)
```
There's a fair bit to break down here, so let's start with what we're trying to achieve with this check. As you can probably guess from the name it's locking a command to a **list of channels**. The inner function named `predicate` is used to perform the actual check on the command context. Here you can do anything that requires a `Context` object. This inner function should return `True` if the check is **successful** or `False` if the check **fails**.

Here's how we might use our new check:
```py
@bot.command(name="ping")
@in_any_channel(728343273562701984)
async def ping(ctx: Context):
  ...
```
This would lock the `ping` command to only be used in the channel `728343273562701984`. If this check function fails it will raise a `CheckFailure` exception, which can be handled in your error handler.
