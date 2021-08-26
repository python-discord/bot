Bot variables are a new type of global variables, meant **only** for discord.py. It is made as an attribute of your existing [commands.Bot](https://discordpy.readthedocs.io/en/latest/ext/commands/api.html#discord.ext.commands.Bot) instance and can be used and accessed **anywhere**, where your bot instance is accessible. An example on how to make a bot variable named `test` is shown below:

```py
bot = commands.Bot(command_prefix="!")
bot.test = "I am accessible everywhere!"

@bot.command()
async def get(ctx: commands.Context):
    """A command to demonstrate how to use a bot variable"""
    await ctx.send(ctx.bot.test) # This will send the text, I am accessible everywhere!

@bot.command()
async def set(ctx: commands.Context, *, new_text: str):
    """A command to demonstrate, how to change the value of a bot variable"""
    # Here we change the attribute to what was specified in new_text
    bot.test = new_text
    print(bot.test) # This will print the text specified in new_text!
```

Bot variables are better than global variables because these variables can be accessed anywhere where your Bot instance is accessible!

*Be sure **not** to overwrite any existing bot attribute, like `cogs` or `users`. Name your bot variables carefully!*
