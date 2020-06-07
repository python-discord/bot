**Cooldowns**

Cooldowns are used in discord.py to rate-limit.
 
```python
from discord.ext import commands

class SomeCog(commands.Cog):
    def __init__(self):
        self._cd = commands.CooldownMapping.from_cooldown(1.0, 60.0, commands.BucketType.user)

    async def cog_check(self, ctx):
        bucket = self._cd.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            # you're rate limited
            # helpful message here
            pass
        # you're not rate limited
```

`from_cooldown` takes the amount of `update_rate_limit()`s needed to trigger the cooldown, the time in which the cooldown is triggered, and a [`BucketType`](discordpy.readthedocs.io/en/latest/ext/commands/api.html#discord.discord.ext.commands.BucketType).
