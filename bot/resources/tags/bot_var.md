Python allows you to set custom attributes to class instances, like your bot! By adding variables as attributes to your bot you can access them anywhere you access you bot. In the discord.py library, these custom attributes are commonly known as `Bot Variables` and can be a lifesaver if your bot is divided into many different files. An example on how to use custom attributes on your bot is shown below:

```py
bot = commands.Bot(command_prefix="!")
# Set an attribute on our bot
bot.test = "I am accessible everywhere!"

@bot.command()
async def get(ctx: commands.Context):
    """A command to get the current value of `test`."""
   await ctx.send(ctx.bot.test) # Send what the test attribute is currently set to

@bot.command()
async def set(ctx: commands.Context, *, new_text: str):
    """A command to set a new value of `test`."""
    # Here we change the attribute to what was specified in new_text
    bot.test = new_text
```

When setting your own custom attributes you can access those variables anywhere you have your bot instance, this becomes extra useful when your bot is split over multiple files. This all applies to cogs as well!

*Be sure **not** to overwrite attributes discord.py uses, like `cogs` or `users`. Name your attributes carefully!*
