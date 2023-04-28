---
embed:
    title: "Message Content Intent"
---

The discord gateway only dispatches events you subscribe to, which you can configure by using "intents." 

Privileged intents, such as message content, have to be explicitly enabled from the [Discord Developer Portal](https://discord.com/developers/applications) in addition to being enabled in the code:

```py
intents = discord.Intents.default() # create a default Intents instance
intents.message_content = True # enable message content intents

bot = commands.Bot(command_prefix="!", intents=intents) # actually pass it into the constructor
```

The message content intent is what determines if an app will receive the actual content of newly created messages. Without this intent, discord.py won't be able to detect prefix commands, so prefix commands won't respond.
