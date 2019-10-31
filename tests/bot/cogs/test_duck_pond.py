import logging
import unittest
from unittest.mock import MagicMock

from bot.cogs import duck_pond
from tests.helpers import MockBot, MockMessage


class DuckPondTest(unittest.TestCase):
    """Tests the `DuckPond` cog."""

    def setUp(self):
        """Adds the cog, a bot, and a message to the instance for usage in tests."""
        self.bot = MockBot()
        self.cog = duck_pond.DuckPond(bot=self.bot)

        self.msg = MockMessage(message_id=555, content='')
        self.msg.author.__str__ = MagicMock()
        self.msg.author.__str__.return_value = 'lemon'
        self.msg.author.bot = False
        self.msg.author.avatar_url_as.return_value = 'picture-lemon.png'
        self.msg.author.id = 42
        self.msg.author.mention = '@lemon'
        self.msg.channel.mention = "#lemonade-stand"

    def test_is_staff_correctly_identifies_staff(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_has_green_checkmark(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_count_custom_duck_emojis(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_count_unicode_duck_emojis(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_count_mixed_duck_emojis(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_raw_reaction_add_rejects_bot(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_raw_reaction_add_rejects_non_staff(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_raw_reaction_add_sends_message_on_valid_input(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_raw_reaction_remove_rejects_non_checkmarks(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass

    def test_raw_reaction_remove_prevents_checkmark_removal(self):
        """A string decoding to numeric characters is a valid user ID."""
        pass


class DuckPondSetupTests(unittest.TestCase):
    """Tests setup of the `DuckPond` cog."""

    def test_setup(self):
        """Setup of the cog should log a message at `INFO` level."""
        bot = MockBot()
        log = logging.getLogger('bot.cogs.duck_pond')

        with self.assertLogs(logger=log, level=logging.INFO) as log_watcher:
            duck_pond.setup(bot)
            line = log_watcher.output[0]

        bot.add_cog.assert_called_once()
        self.assertIn("Cog loaded: DuckPond", line)
