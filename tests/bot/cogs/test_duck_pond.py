import logging
import unittest

from bot.cogs import duck_pond
from tests.helpers import MockBot, MockMember, MockMessage, MockReaction, MockRole


class DuckPondTest(unittest.TestCase):
    """Tests the `DuckPond` cog."""

    def setUp(self):
        """Adds the cog, a bot, and the mocks we'll need for our tests."""
        self.bot = MockBot()
        self.cog = duck_pond.DuckPond(bot=self.bot)

        # Set up some roles
        self.admin_role = MockRole(name="Admins", role_id=476190234653229056)
        self.contrib_role = MockRole(name="Contributor", role_id=476190302659543061)

        # Set up some users
        self.admin_member = MockMember(roles=(self.admin_role,))
        self.contrib_member = MockMember(roles=(self.contrib_role,))
        self.no_role_member = MockMember()

        # Set up emojis
        self.checkmark_emoji = "✅"
        self.thumbs_up_emoji = "👍"

        # Set up reactions
        self.checkmark_reaction = MockReaction(emoji=self.checkmark_emoji)
        self.thumbs_up_reaction = MockReaction(emoji=self.thumbs_up_emoji)

        # Set up a messages
        self.checkmark_message = MockMessage(reactions=(self.checkmark_reaction,))
        self.thumbs_up_message = MockMessage(reactions=(self.thumbs_up_reaction,))
        self.no_reaction_message = MockMessage()

    def test_is_staff_correctly_identifies_staff(self):
        """Test that is_staff correctly identifies a staff member."""
        with self.subTest():
            self.assertTrue(duck_pond.DuckPond.is_staff(self.admin_member))
            self.assertFalse(duck_pond.DuckPond.is_staff(self.contrib_member))
            self.assertFalse(duck_pond.DuckPond.is_staff(self.no_role_member))

    def test_has_green_checkmark_correctly_identifies_messages(self):
        """Test that has_green_checkmark recognizes messages with checkmarks."""
        with self.subTest():
            self.assertTrue(duck_pond.DuckPond.has_green_checkmark(self.checkmark_message))
            self.assertFalse(duck_pond.DuckPond.has_green_checkmark(self.thumbs_up_message))
            self.assertFalse(duck_pond.DuckPond.has_green_checkmark(self.no_reaction_message))

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
