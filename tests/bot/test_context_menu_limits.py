import unittest

import discord

from bot.exts.filtering.filtering import Filtering
from bot.exts.info.information import Information
from bot.exts.moderation.clean import Clean
from bot.exts.moderation.infraction.infractions import Infractions
from bot.exts.moderation.watchchannels.bigbrother import BigBrother
from bot.exts.recruitment.talentpool._cog import TalentPool
from bot.exts.utils.reminders import Reminders
from tests import helpers

# Discord allows at most this many menus of each type per guild.
MAX_MENUS_PER_TYPE = 5


class ContextMenuLimitTests(unittest.TestCase):
    """Tests that the context menus of all cogs fit within Discord's limits."""

    def test_menus_are_within_limits(self):
        # The menus are registered on the tree of the bot, which is a mock, so collect them from the cogs.
        bot = helpers.MockBot()
        cogs = [
            Information(bot), Reminders(bot), Clean(bot), TalentPool(bot),
            Infractions(bot), BigBrother(bot), Filtering(bot),
        ]
        menus = [m for cog in cogs for m in vars(cog).values() if isinstance(m, discord.app_commands.ContextMenu)]

        for menu_type in (discord.AppCommandType.user, discord.AppCommandType.message):
            with self.subTest(menu_type=menu_type):
                names = [m.name for m in menus if m.type is menu_type]
                self.assertEqual(len(names), len(set(names)))
                self.assertLessEqual(len(names), MAX_MENUS_PER_TYPE, names)

        for menu in menus:
            with self.subTest(menu=menu.name):
                self.assertLessEqual(len(menu.name), 32)
