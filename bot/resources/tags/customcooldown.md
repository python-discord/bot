**Cooldowns**

Cooldowns can be used in discord.py to rate-limit. In this example, we're using it in an on_message.

```python
from discord.ext import commands

_cd = commands.CooldownMapping.from_cooldown(1.0, 60.0, commands.BucketType.user)

@bot.event
async def on_message(message):
    bucket = _cd.get_bucket(message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        await message.channel.send("Slow down! You're sending messages too fast")
        pass
    # you're not rate limited
```

`from_cooldown` takes the amount of `update_rate_limit()`s needed to trigger the cooldown, the time in which the cooldown is triggered, and a [`BucketType`](discordpy.readthedocs.io/en/latest/ext/commands/api.html#discord.discord.ext.commands.BucketType).
