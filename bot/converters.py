import json
import random

import discord
from discord.ext.commands import Converter
from fuzzywuzzy import fuzz

from bot.utils import disambiguate


class Snake(Converter):
    with open('snakes.json', 'r') as f:
        snakes = json.load(f)

    async def convert(self, ctx, name):
        name = name.lower()

        if name == 'python':
            return 'Python (programming language)'

        def get_potential(iterable, *, threshold=80):
            nonlocal name
            potential = []

            for item in iterable:
                original, item = item, item.lower()

                if name == item:
                    return [original]

                a, b = fuzz.ratio(name, item), fuzz.partial_ratio(name, item)
                if a >= threshold or b >= threshold:
                    potential.append(original)

            return potential

        all_names = self.snakes.keys() | self.snakes.values()
        timeout = len(all_names) * (3 / 4)

        embed = discord.Embed(title='Found multiple choices. Please choose the correct one.', colour=0x59982F)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)

        name = await disambiguate(ctx, get_potential(all_names), timeout=timeout, embed=embed)
        return self.snakes.get(name, name)

    @classmethod
    def random(cls):
        # list cast necessary because choice() uses indexing internally
        return random.choice(list(cls.snakes.values()))
