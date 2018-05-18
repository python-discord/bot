import random
import socket

import discord
from aiohttp import AsyncResolver, ClientSession, TCPConnector
from discord.ext.commands import Converter
from fuzzywuzzy import fuzz

from bot.constants import DEBUG_MODE, SITE_API_KEY, SITE_API_URL
from bot.utils import disambiguate

NAMES_URL = f"{SITE_API_URL}/snake_names"
SPECIAL_URL = f"{SITE_API_URL}/special_snakes"


class Snake(Converter):
    snakes = None
    special_cases = None

    async def convert(self, ctx, name):
        await self.build_list()
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

        # Handle special cases
        if name.lower() in self.special_cases:
            return self.special_cases.get(name.lower(), name.lower())

        names = {snake['name']: snake['scientific'] for snake in self.snakes}
        all_names = names.keys() | names.values()
        timeout = len(all_names) * (3 / 4)

        embed = discord.Embed(title='Found multiple choices. Please choose the correct one.', colour=0x59982F)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)

        name = await disambiguate(ctx, get_potential(all_names), timeout=timeout, embed=embed)
        return names.get(name, name)

    @classmethod
    async def build_list(cls):

        headers = {"X-API-KEY": SITE_API_KEY}

        # Set up the session
        if DEBUG_MODE:
            http_session = ClientSession(
                connector=TCPConnector(
                    resolver=AsyncResolver(),
                    family=socket.AF_INET,
                    verify_ssl=False,
                )
            )
        else:
            http_session = ClientSession(
                connector=TCPConnector(
                    resolver=AsyncResolver()
                )
            )

        # Get all the snakes
        if cls.snakes is None:
            response = await http_session.get(
                NAMES_URL,
                params={"get_all": "true"},
                headers=headers
            )
            cls.snakes = await response.json()

        # Get the special cases
        if cls.special_cases is None:
            response = await http_session.get(
                SPECIAL_URL,
                headers=headers
            )
            special_cases = await response.json()
            cls.special_cases = {snake['name'].lower(): snake for snake in special_cases}

        # Close the session
        http_session.close()

    @classmethod
    async def random(cls):
        """
        This is stupid. We should find a way to
        somehow get the global session into a
        global context, so I can get it from here.
        :return:
        """

        await cls.build_list()
        names = [snake['scientific'] for snake in cls.snakes]
        return random.choice(names)
