---
embed:
    title: "The discord.py `on_message` event"
---

Registering the `on_message` event with [`@bot.event`](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.Bot.event) will override the default behavior of the event. This may cause prefix commands to stop working, because they rely on the default `on_message` event handler.

Instead, use [`@bot.listen`](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.Bot.listen) to add a listener. Listeners get added alongside the default `on_message` handler which allows you to have multiple handlers for the same event. This means prefix commands can still be invoked as usual. Here's an example:
```python
@bot.listen()
async def on_message(message):
    ...  # do stuff here

# Or...

@bot.listen('on_message')
async def message_listener(message):
    ...  # do stuff here
```
You can also tell discord.py to process the message for commands as usual at the end of the `on_message` handler with [`bot.process_commands()`](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.Bot.process_commands). However, this method isn't recommended as it does not allow you to add multiple `on_message` handlers.

If your prefix commands are still not working, it may be because you haven't enabled the `message_content` intent. See `/tag message_content` for more info.
