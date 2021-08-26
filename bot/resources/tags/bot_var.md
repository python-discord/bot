Python allows you to set custom attributes to instances and your bot is one such instance. You can add custom attributes to your bot instance and access them **anywhere** you access you bot. In the discord.py library, these custom attributes are commonly known as `Bot Variables` and these can be a lifesaver if your bot is divided into many different files. An example on how to make a bot variable named `test` is shown below:

```py
bot = commands.Bot(command_prefix="!")
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
    print(bot.test) # This will print the text specified in new_text!
```

Why are bot variables preferred over global variables? Because you can access those variables **anywhere** your bot instance is accessible, be that be the same or a different file.

*Be sure **not** to overwrite any existing attribute, like `cogs` or `users`. Name your attributes carefully!*
