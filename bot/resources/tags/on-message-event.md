---
embed:
    title: "The `on_message` event"
---

When defining an `on_message` event handler, prefix commands may stop working as it overrides the default behaviour of the `on_message` event.

Instead, use [`@bot.listen`](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.Bot.listen) to add a listener. Listeners get added alongside the default `on_message` event, preventing an override of on_message, and allowing prefix commands to still be invoked.

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
