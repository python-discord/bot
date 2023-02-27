---
embed:
    title: "Cooldowns in discord.py"
---
Cooldowns can be used in discord.py to rate-limit. In this example, we're using it in an on_message.

```python
from discord.ext import commands

message_cooldown = commands.CooldownMapping.from_cooldown(1.0, 60.0, commands.BucketType.user)

@bot.event
async def on_message(message):
    bucket = message_cooldown.get_bucket(message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        await message.channel.send(f"Slow down! Try again in {retry_after} seconds.")
    else:
        await message.channel.send("Not ratelimited!")
```

`from_cooldown` takes the amount of `update_rate_limit()`s needed to trigger the cooldown, the time in which the cooldown is triggered, and a [`BucketType`](https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.BucketType).
