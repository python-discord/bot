import asyncio
import logging
import unittest
from unittest.mock import MagicMock

from bot import constants
from bot.cogs import duck_pond
from tests.helpers import MockBot, MockEmoji, MockMember, MockMessage, MockReaction, MockRole, MockTextChannel


class DuckPondTest(unittest.TestCase):
    """Tests the `DuckPond` cog."""

    def setUp(self):
        """Adds the cog, a bot, and the mocks we'll need for our tests."""
        self.bot = MockBot()
        self.cog = duck_pond.DuckPond(bot=self.bot)

        # Set up some constants
        self.CHANNEL_ID = 555
        self.MESSAGE_ID = 666
        self.BOT_ID = 777
        self.CONTRIB_ID = 888
        self.ADMIN_ID = 999

        # Override the constants we'll be needing
        constants.STAFF_ROLES = (123,)
        constants.DuckPond.custom_emojis = (789,)
        constants.DuckPond.threshold = 1

        # Set up some roles
        self.admin_role = MockRole(name="Admins", role_id=123)
        self.contrib_role = MockRole(name="Contributor", role_id=456)

        # Set up some users
        self.admin_member_1 = MockMember(roles=(self.admin_role,), id=self.ADMIN_ID)
        self.admin_member_2 = MockMember(roles=(self.admin_role,), id=911)
        self.contrib_member = MockMember(roles=(self.contrib_role,), id=self.CONTRIB_ID)
        self.bot_member = MockMember(roles=(self.contrib_role,), id=self.BOT_ID, bot=True)
        self.no_role_member = MockMember()

        # Set up emojis
        self.checkmark_emoji = "✅"
        self.thumbs_up_emoji = "👍"
        self.unicode_duck_emoji = "🦆"
        self.yellow_ducky_emoji = MockEmoji(id=789)

        # Set up reactions
        self.checkmark_reaction = MockReaction(
            emoji=self.checkmark_emoji,
            user_list=[self.admin_member_1]
        )
        self.thumbs_up_reaction = MockReaction(
            emoji=self.thumbs_up_emoji,
            user_list=[self.admin_member_1, self.contrib_member]
        )
        self.yellow_ducky_reaction = MockReaction(
            emoji=self.yellow_ducky_emoji,
            user_list=[self.admin_member_1, self.contrib_member]
        )
        self.unicode_duck_reaction_1 = MockReaction(
            emoji=self.unicode_duck_emoji,
            user_list=[self.admin_member_1]
        )
        self.unicode_duck_reaction_2 = MockReaction(
            emoji=self.unicode_duck_emoji,
            user_list=[self.admin_member_2]
        )
        self.bot_reaction = MockReaction(
            emoji=self.yellow_ducky_emoji,
            user_list=[self.bot_member]
        )
        self.contrib_reaction = MockReaction(
            emoji=self.yellow_ducky_emoji,
            user_list=[self.contrib_member]
        )

        # Set up a messages
        self.checkmark_message = MockMessage(reactions=(self.checkmark_reaction,))
        self.thumbs_up_message = MockMessage(reactions=(self.thumbs_up_reaction,))
        self.yellow_ducky_message = MockMessage(reactions=(self.yellow_ducky_reaction,))
        self.unicode_duck_message = MockMessage(reactions=(self.unicode_duck_reaction_1,))
        self.double_unicode_duck_message = MockMessage(
            reactions=(self.unicode_duck_reaction_1, self.unicode_duck_reaction_2)
        )
        self.double_mixed_duck_message = MockMessage(
            reactions=(self.unicode_duck_reaction_1, self.yellow_ducky_reaction)
        )

        self.bot_message = MockMessage(reactions=(self.bot_reaction,))
        self.contrib_message = MockMessage(reactions=(self.contrib_reaction,))
        self.no_reaction_message = MockMessage()

        # Set up some channels
        self.text_channel = MockTextChannel(id=self.CHANNEL_ID)

    @staticmethod
    def _mock_send_webhook(content, username, avatar_url, embed):
        """Mock for the send_webhook method in DuckPond"""

    def test_is_staff_correctly_identifies_staff(self):
        """Test that is_staff correctly identifies a staff member."""
        with self.subTest():
            self.assertTrue(self.cog.is_staff(self.admin_member_1))
            self.assertFalse(self.cog.is_staff(self.contrib_member))
            self.assertFalse(self.cog.is_staff(self.no_role_member))

    def test_has_green_checkmark_correctly_identifies_messages(self):
        """Test that has_green_checkmark recognizes messages with checkmarks."""
        with self.subTest():
            self.assertTrue(self.cog.has_green_checkmark(self.checkmark_message))
            self.assertFalse(self.cog.has_green_checkmark(self.thumbs_up_message))
            self.assertFalse(self.cog.has_green_checkmark(self.no_reaction_message))

    def test_count_custom_duck_emojis(self):
        """Test that count_ducks counts custom ducks correctly."""
        count_no_ducks = self.cog.count_ducks(self.thumbs_up_message)
        count_one_duck = self.cog.count_ducks(self.yellow_ducky_message)
        with self.subTest():
            self.assertEqual(asyncio.run(count_no_ducks), 0)
            self.assertEqual(asyncio.run(count_one_duck), 1)

    def test_count_unicode_duck_emojis(self):
        """Test that count_ducks counts unicode ducks correctly."""
        count_one_duck = self.cog.count_ducks(self.unicode_duck_message)
        count_two_ducks = self.cog.count_ducks(self.double_unicode_duck_message)

        with self.subTest():
            self.assertEqual(asyncio.run(count_one_duck), 1)
            self.assertEqual(asyncio.run(count_two_ducks), 2)

    def test_count_mixed_duck_emojis(self):
        """Test that count_ducks counts mixed ducks correctly."""
        count_two_ducks = self.cog.count_ducks(self.double_mixed_duck_message)

        with self.subTest():
            self.assertEqual(asyncio.run(count_two_ducks), 2)

    def test_raw_reaction_add_rejects_bot(self):
        """Test that send_webhook is not called if the user is a bot."""
        self.text_channel.fetch_message.return_value = self.bot_message
        self.bot.get_all_channels.return_value = (self.text_channel,)

        payload = MagicMock(  # RawReactionActionEvent
            channel_id=self.CHANNEL_ID,
            message_id=self.MESSAGE_ID,
            user_id=self.BOT_ID,
        )

        with self.subTest():
            asyncio.run(self.cog.on_raw_reaction_add(payload))
            self.bot.cog.send_webhook.assert_not_called()

    def test_raw_reaction_add_rejects_non_staff(self):
        """Test that send_webhook is not called if the user is not a member of staff."""
        self.text_channel.fetch_message.return_value = self.contrib_message
        self.bot.get_all_channels.return_value = (self.text_channel,)

        payload = MagicMock(  # RawReactionActionEvent
            channel_id=self.CHANNEL_ID,
            message_id=self.MESSAGE_ID,
            user_id=self.CONTRIB_ID,
        )

        with self.subTest():
            asyncio.run(self.cog.on_raw_reaction_add(payload))
            self.bot.cog.send_webhook.assert_not_called()

    def test_raw_reaction_add_sends_message_on_valid_input(self):
        """Test that send_webhook is called if payload is valid."""
        self.text_channel.fetch_message.return_value = self.unicode_duck_message
        self.bot.get_all_channels.return_value = (self.text_channel,)

        payload = MagicMock(  # RawReactionActionEvent
            channel_id=self.CHANNEL_ID,
            message_id=self.MESSAGE_ID,
            user_id=self.ADMIN_ID,
        )

        with self.subTest():
            asyncio.run(self.cog.on_raw_reaction_add(payload))
            self.bot.cog.send_webhook.assert_called_once()

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
