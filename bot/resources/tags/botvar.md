---
embed:
    title: "Bot variables"
---
Python allows you to set custom attributes to most objects, like your bot! By storing things as attributes of the bot object, you can access them anywhere you access your bot. In the discord.py library, these custom attributes are commonly known as "bot variables" and can be a lifesaver if your bot is divided into many different files. An example on how to use custom attributes on your bot is shown below:

```py
bot = commands.Bot(command_prefix="!")
# Set an attribute on our bot
bot.test = "I am accessible everywhere!"

@bot.command()
async def get(ctx: commands.Context):
    """A command to get the current value of `test`."""
    # Send what the test attribute is currently set to
    await ctx.send(ctx.bot.test)

@bot.command()
async def setval(ctx: commands.Context, *, new_text: str):
    """A command to set a new value of `test`."""
    # Here we change the attribute to what was specified in new_text
    bot.test = new_text
```

This all applies to cogs as well! You can set attributes to `self` as you wish.

*Be sure **not** to overwrite attributes discord.py uses, like `cogs` or `users`. Name your attributes carefully!*
