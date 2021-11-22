# How to Create A Slash command or context-menus in d.py`v2.0`

Firstly install [`dpy-appcommands`](https://PyPi.org/project/dpy-appcommands) by
```sh
python3 -m pip install dpy-appcommands -U
```

And make bot like this
```py
import appcommands

bot = appcommands.Bot(command_prefix="$")
```

And make a `/` cmd
```py
@bot.slashcommand(name="id")
async def id(ctx, user: discord.Member = None):
  user = user or ctx.author
  await ctx.send(
    f"Id of {user.mention} is {user.id}",
    ephemeral=True
  )
```

Or read the full docs [`here`](https://dpy-appcommands.rtfd.io)
