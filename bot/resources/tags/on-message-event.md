---
embed:
    title: "The `on_message` event"
---

Registering the `on_message` event with [`@bot.event`](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.Bot.event) will override the default behavior of the event. This may cause prefix commands to stop working, because they rely on the default `on_message` event.

Instead, use [`@bot.listen`](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.Bot.listen) to add a listener. Listeners get added alongside the default `on_message` event, rather than overriding it, so prefix commands can still be invoked as usual:

```python
@bot.listen('on_message')
async def message_listener(message):
    ...  # do stuff here
```

You can also tell discord.py to process commands as usual after you're done processing messages with [`bot.process_commands()`](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.Bot.process_commands). However, this method isn't recommended as it does not allow you to add multiple `on_message` handlers.

```python
@bot.event
async def on_message(message):
    ...  # do stuff here

    await bot.process_commands(message)
```

If your prefix commands are still not working, it may be because you need the `message_content` intent. See `!tag message_content` for more info.
