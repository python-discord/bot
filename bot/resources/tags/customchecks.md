---
embed:
    title: "Custom command checks in discord.py"
---
Often you may find the need to use checks that don't exist by default in discord.py. Fortunately, discord.py provides `discord.ext.commands.check` which allows you to create you own checks like this:
```py
from discord.ext.commands import check, Context

def in_any_channel(*channels):
  async def predicate(ctx: Context):
    return ctx.channel.id in channels
  return check(predicate)
```
This check is to check whether the invoked command is in a given set of channels. The inner function, named `predicate` here, is used to perform the actual check on the command, and check logic should go in this function. It must be an async function, and always provides a single `commands.Context` argument which you can use to create check logic. This check function should return a boolean value indicating whether the check passed (return `True`) or failed (return `False`).

The check can now be used like any other commands check as a decorator of a command, such as this:
```py
@bot.command(name="ping")
@in_any_channel(728343273562701984)
async def ping(ctx: Context):
  ...
```
This would lock the `ping` command to only be used in the channel `728343273562701984`. If this check function fails it will raise a `CheckFailure` exception, which can be handled in your error handler.
