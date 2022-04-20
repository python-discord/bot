import unittest

import rapidfuzz

from bot.exts.info import help
from tests.helpers import MockBot, MockContext, autospec


class HelpCogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        """Attach an instance of the cog to the class for tests."""
        self.bot = MockBot()
        self.cog = help.Help(self.bot)
        self.ctx = MockContext(bot=self.bot)

    @autospec(help.CustomHelpCommand, "get_all_help_choices", return_value={"help"}, pass_mocks=False)
    async def test_help_fuzzy_matching(self):
        """Test fuzzy matching of commands when called from help."""
        result = await self.bot.help_command.command_not_found("holp")

        match = {"help": rapidfuzz.fuzz.ratio("help", "holp")}
        self.assertEqual(match, result.possible_matches)
