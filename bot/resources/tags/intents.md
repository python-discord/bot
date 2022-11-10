**Using intents in discord.py**

Intents are a feature of Discord that tells the gateway exactly which events to send your bot. Various features of discord.py rely on having particular intents enabled. Since discord.py v2.0.0, this has become **mandatory** for developers to define in their code.

There are *standard* intents and *privileged* intents. The current privileged intents are `Presences`, `Server Members`, and `Message Content`. To use one of the privileged intents, you have to first enable them in the [Discord Developer Portal](https://discord.com/developers/applications). Go to the `Bot` page of your application, scroll down to the `Privileged Gateway Intents` section, and enable the privileged intents that you need.

Afterwards in your code, you need to set the intents you want to connect with in the bot's constructor using the `intents` keyword argument, like this:
```py
from discord import Intents
from discord.ext import commands

intents = Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
```
For more info about using intents, see the [discord.py docs on intents](https://discordpy.readthedocs.io/en/latest/intents.html), and for general information about them, see the [Discord developer documentation on intents](https://discord.com/developers/docs/topics/gateway#gateway-intents).
