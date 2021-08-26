Bot variables are a new type of global variables, meant **only** for discord.py. It is an attribute of your existing [commands.Bot](https://discordpy.readthedocs.io/en/latest/ext/commands/api.html#discord.ext.commands.Bot) instance and can be used and accessed **anywhere**, where your bot instance is accessible. An example, on how to make a bot variable named `test` is shown below!

```py
bot = commands.Bot(...)
bot.test = "I am accessible everywhere!"

# In the same file
@bot.command()
async def foo(ctx: commands.Context):
    """A command to demonstrate how to use a bot variable"""
    await ctx.send(bot.test) # This will send the text, I am accessible everywhere!

@bot.command()
async def bar(ctx: commands.Context, *, new_text: str):
    """A command to demonstrate, how to change the value of a bot variable"""
    bot.test = new_text
    print(bot.test) # This will print the text u specified in new_text!

```

As said that these variables are accessible everywhere your commands.Bot instance is accessible, usage of these variables in a [commands.Cog](https://discordpy.readthedocs.io/en/latest/ext/commands/api.html#cog) is also shown below.

```py
# In the main bot file
bot = commands.Bot(...)
bot.test = "I am accessible anywhere, even in a Cog!"

# In a commands.Cog file
@commands.command()
async def foo(self, ctx: commands.Context):
    """A command to demonstrate how to use a bot variable in a commands.Cog"""
    await ctx.send(ctx.bot.test) # As ctx.bot returns the commands.Bot instance, you can simply do ctx.bot.test to access that variable.

# In an event
@commands.Cog.listener()
async def on_message(self, message: discord.Message):
    if message.content == "bot var":
        await message.channel.send(self.bot.test) # This will only work if u have specified the commands.Bot instance in your Cog's init.
```

Bot variables are better than global variables because these variables can be accessed anywhere where your Bot instance is accessible!

⚠️ Be sure **not** to overwrite any existing bot attribute, like `cogs` or `users`. Name your bot variables carefully!
