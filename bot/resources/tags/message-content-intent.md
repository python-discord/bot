---
aliases: ["mcintent", "message_content", "message_content_intent"]
embed:
    title: "Discord Message Content Intent"
---

The Discord gateway only dispatches events you subscribe to, which you can configure by using "intents."

The message content intent is what determines if an app will receive the actual content of newly created messages. Without this intent, discord.py won't be able to detect prefix commands, so prefix commands won't respond.

Privileged intents, such as message content, have to be explicitly enabled from the [Discord Developer Portal](https://discord.com/developers/applications) in addition to being enabled in the code:

```py
intents = discord.Intents.default() # create a default Intents instance
intents.message_content = True # enable message content intents

bot = commands.Bot(command_prefix="!", intents=intents) # actually pass it into the constructor
```
For more information on intents, see `/tag intents`. If prefix commands are still not working, see `/tag on-message-event`.
