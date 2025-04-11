import unittest

from discord import Colour, Embed
from discord.ext.commands import BadArgument

from bot.exts.utils.utils import Utils, ZEN_OF_PYTHON
from tests.helpers import MockBot, MockContext


class ZenTests(unittest.IsolatedAsyncioTestCase):
    """ Tests for the `!zen` command. """


    def setUp(self):
        self.bot = MockBot()
        self.cog = Utils(self.bot)
        self.ctx = MockContext()

        self.zen_list = ZEN_OF_PYTHON.splitlines()
        self.template_embed = Embed(colour=Colour.og_blurple(), title="The Zen of Python", description=ZEN_OF_PYTHON)



    async def test_zen_without_arguments(self):
        """ Tests if the `!zen` command reacts properly to no arguments. """
        self.template_embed.title += ", by Tim Peters"


        await self.cog.zen.callback(self.cog,self.ctx, search_value = None)
        self.ctx.send.assert_called_once_with(embed=self.template_embed)

    async def test_zen_with_valid_index(self):
        """ Tests if the `!zen` command reacts properly to a valid index as an argument. """
        expected_results = {
            0: ("The Zen of Python (line 0):", "Beautiful is better than ugly."),
            10: ("The Zen of Python (line 10):", "Unless explicitly silenced."),
            18: ("The Zen of Python (line 18):", "Namespaces are one honking great idea -- let's do more of those!"),
            -1: ("The Zen of Python (line 18):", "Namespaces are one honking great idea -- let's do more of those!"),
            -10: ("The Zen of Python (line 9):", "Errors should never pass silently."),
            -19: ("The Zen of Python (line 0):", "Beautiful is better than ugly.")

        }

        for index, (title, description) in expected_results.items():
            self.template_embed.title =  title
            self.template_embed.description = description
            ctx = MockContext()
            with self.subTest(index = index, expected_title=title, expected_description = description):
                await self.cog.zen.callback(self.cog, ctx, search_value = str(index))
                ctx.send.assert_called_once_with(embed = self.template_embed)



    async def test_zen_with_invalid_index(self):
        """ Tests if the `!zen` command reacts properly to an out-of-bounds index as an argument. """
        # Negative index
        with self.subTest(index = -20), self.assertRaises(BadArgument):
            await self.cog.zen.callback(self.cog, self.ctx, search_value="-20")

        # Positive index
        with self.subTest(index = len(ZEN_OF_PYTHON)), self.assertRaises(BadArgument):
            await self.cog.zen.callback(self.cog, self.ctx, search_value=str(len(ZEN_OF_PYTHON)))

    async def test_zen_with_valid_slices(self):
        """ Tests if the `!zen` command reacts properly to valid slices for indexing as an argument. """

        expected_results = {
            "0:19": ("The Zen of Python, by Tim Peters", "\n".join(self.zen_list)),
            ":": ("The Zen of Python, by Tim Peters", "\n".join(self.zen_list)),
            "::": ("The Zen of Python, by Tim Peters", "\n".join(self.zen_list)),
            "1:": ("The Zen of Python (lines 1-18):", "\n".join(self.zen_list[1:])),
            "-2:-1": ("The Zen of Python (line 17):", self.zen_list[17]),
            "0:-1": ("The Zen of Python (lines 0-17):", "\n".join(self.zen_list[0:-1])),
            "10:13": ("The Zen of Python (lines 10-12):", "\n".join(self.zen_list[10:13])),
            "::-1": ("The Zen of Python (step size -1):", "\n".join(self.zen_list[::-1])),
            "10:5:-1": ("The Zen of Python (lines 6-10, step size -1):", "\n".join(self.zen_list[10:5:-1])),
        }

        for input_slice, (title, description) in expected_results.items():
            self.template_embed.title = title
            self.template_embed.description = description

            ctx = MockContext()
            with self.subTest(input_slice=input_slice, expected_title=title, expected_description=description):
                await self.cog.zen.callback(self.cog, ctx, search_value=input_slice)
                ctx.send.assert_called_once_with(embed = self.template_embed)

    async def test_zen_with_invalid_slices(self):
        """ Tests if the `!zen` command reacts properly to invalid slices for indexing as an argument. """
        slices= ["19:18", "10:9", "-1:-2", "0:-100", "::0", "1:2:-1", "-5:-4:-1"]

        for input_slice in slices:
            with self.subTest(input_slice = input_slice), self.assertRaises(BadArgument):
                await self.cog.zen.callback(self.cog, self.ctx, search_value=input_slice)