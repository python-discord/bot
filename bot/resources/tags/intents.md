**Using intents in discord.py**

Intents are a feature of Discord that tells the gateway exactly which events to send your bot. By default, discord.py has all intents enabled, except for the `Members` and `Presences` intents, which are needed for events such as `on_member` and to get members' statuses.

To enable one of these intents, you need to first go to the [Discord developer portal](https://discord.com/developers/applications), then to the bot page of your bot's application. Scroll down to the `Privileged Gateway Intents` section, then enable the intents that you need.

Next, in your bot you need to set the intents you want to connect with in the bot's constructor using the `intents` keyword argument, like this:

```py
from discord import Intents
from discord.ext import commands

intents = Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
```

For more info about using intents, see the [discord.py docs on intents](https://discordpy.readthedocs.io/en/latest/intents.html), and for general information about them, see the [Discord developer documentation on intents](https://discord.com/developers/docs/topics/gateway#gateway-intents).
