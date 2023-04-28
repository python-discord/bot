---
embed:
    title: "Message Content Intent"
---

The discord gateway only dispatches events you subscribe to, which you can configure by using "intents"

The message content intent is what determines if an app will receive the actual content of newly created messages. Without this intent, discord.py wouldn't know which command handler to trigger so none of your commands will work.


```py
intents = discord.Intents.default() # create a default Intents instance
intents.message_content = True # enable message content intents

bot = commands.Bot(command_prefix="!", intents=intents) # actually pass it into the constructor
