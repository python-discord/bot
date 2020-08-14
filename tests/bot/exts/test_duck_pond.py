import asyncio
import logging
import typing
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot import constants
from bot.exts import duck_pond
from tests import base
from tests import helpers

MODULE_PATH = "bot.exts.duck_pond"


class DuckPondTests(base.LoggingTestsMixin, unittest.IsolatedAsyncioTestCase):
    """Tests for DuckPond functionality."""

    @classmethod
    def setUpClass(cls):
        """Sets up the objects that only have to be initialized once."""
        cls.nonstaff_member = helpers.MockMember(name="Non-staffer")

        cls.staff_role = helpers.MockRole(name="Staff role", id=constants.STAFF_ROLES[0])
        cls.staff_member = helpers.MockMember(name="staffer", roles=[cls.staff_role])

        cls.checkmark_emoji = "\N{White Heavy Check Mark}"
        cls.thumbs_up_emoji = "\N{Thumbs Up Sign}"
        cls.unicode_duck_emoji = "\N{Duck}"
        cls.duck_pond_emoji = helpers.MockPartialEmoji(id=constants.DuckPond.custom_emojis[0])
        cls.non_duck_custom_emoji = helpers.MockPartialEmoji(id=123)

    def setUp(self):
        """Sets up the objects that need to be refreshed before each test."""
        self.bot = helpers.MockBot(user=helpers.MockMember(id=46692))
        self.cog = duck_pond.DuckPond(bot=self.bot)

    def test_duck_pond_correctly_initializes(self):
        """`__init__ should set `bot` and `webhook_id` attributes and schedule `fetch_webhook`."""
        bot = helpers.MockBot()
        cog = MagicMock()

        duck_pond.DuckPond.__init__(cog, bot)

        self.assertEqual(cog.bot, bot)
        self.assertEqual(cog.webhook_id, constants.Webhooks.duck_pond)
        bot.loop.create_task.assert_called_once_with(cog.fetch_webhook())

    def test_fetch_webhook_succeeds_without_connectivity_issues(self):
        """The `fetch_webhook` method waits until `READY` event and sets the `webhook` attribute."""
        self.bot.fetch_webhook.return_value = "dummy webhook"
        self.cog.webhook_id = 1

        asyncio.run(self.cog.fetch_webhook())

        self.bot.wait_until_guild_available.assert_called_once()
        self.bot.fetch_webhook.assert_called_once_with(1)
        self.assertEqual(self.cog.webhook, "dummy webhook")

    def test_fetch_webhook_logs_when_unable_to_fetch_webhook(self):
        """The `fetch_webhook` method should log an exception when it fails to fetch the webhook."""
        self.bot.fetch_webhook.side_effect = discord.HTTPException(response=MagicMock(), message="Not found.")
        self.cog.webhook_id = 1

        log = logging.getLogger('bot.exts.duck_pond')
        with self.assertLogs(logger=log, level=logging.ERROR) as log_watcher:
            asyncio.run(self.cog.fetch_webhook())

        self.bot.wait_until_guild_available.assert_called_once()
        self.bot.fetch_webhook.assert_called_once_with(1)

        self.assertEqual(len(log_watcher.records), 1)

        record = log_watcher.records[0]
        self.assertEqual(record.levelno, logging.ERROR)

    def test_is_staff_returns_correct_values_based_on_instance_passed(self):
        """The `is_staff` method should return correct values based on the instance passed."""
        test_cases = (
            (helpers.MockUser(name="User instance"), False),
            (helpers.MockMember(name="Member instance without staff role"), False),
            (helpers.MockMember(name="Member instance with staff role", roles=[self.staff_role]), True)
        )

        for user, expected_return in test_cases:
            actual_return = self.cog.is_staff(user)
            with self.subTest(user_type=user.name, expected_return=expected_return, actual_return=actual_return):
                self.assertEqual(expected_return, actual_return)

    async def test_has_green_checkmark_correctly_detects_presence_of_green_checkmark_emoji(self):
        """The `has_green_checkmark` method should only return `True` if one is present."""
        test_cases = (
            (
                "No reactions", helpers.MockMessage(), False
            ),
            (
                "No green check mark reactions",
                helpers.MockMessage(reactions=[
                    helpers.MockReaction(emoji=self.unicode_duck_emoji, users=[self.bot.user]),
                    helpers.MockReaction(emoji=self.thumbs_up_emoji, users=[self.bot.user])
                ]),
                False
            ),
            (
                "Green check mark reaction, but not from our bot",
                helpers.MockMessage(reactions=[
                    helpers.MockReaction(emoji=self.unicode_duck_emoji, users=[self.bot.user]),
                    helpers.MockReaction(emoji=self.checkmark_emoji, users=[self.staff_member])
                ]),
                False
            ),
            (
                "Green check mark reaction, with one from the bot",
                helpers.MockMessage(reactions=[
                    helpers.MockReaction(emoji=self.unicode_duck_emoji, users=[self.bot.user]),
                    helpers.MockReaction(emoji=self.checkmark_emoji, users=[self.staff_member, self.bot.user])
                ]),
                True
            )
        )

        for description, message, expected_return in test_cases:
            actual_return = await self.cog.has_green_checkmark(message)
            with self.subTest(
                test_case=description,
                expected_return=expected_return,
                actual_return=actual_return
            ):
                self.assertEqual(expected_return, actual_return)

    def _get_reaction(
        self,
        emoji: typing.Union[str, helpers.MockEmoji],
        staff: int = 0,
        nonstaff: int = 0
    ) -> helpers.MockReaction:
        staffers = [helpers.MockMember(roles=[self.staff_role]) for _ in range(staff)]
        nonstaffers = [helpers.MockMember() for _ in range(nonstaff)]
        return helpers.MockReaction(emoji=emoji, users=staffers + nonstaffers)

    async def test_count_ducks_correctly_counts_the_number_of_eligible_duck_emojis(self):
        """The `count_ducks` method should return the number of unique staffers who gave a duck."""
        test_cases = (
            # Simple test cases
            # A message without reactions should return 0
            (
                "No reactions",
                helpers.MockMessage(),
                0
            ),
            # A message with a non-duck reaction from a non-staffer should return 0
            (
                "Non-duck reaction from non-staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.thumbs_up_emoji, nonstaff=1)]),
                0
            ),
            # A message with a non-duck reaction from a staffer should return 0
            (
                "Non-duck reaction from staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.non_duck_custom_emoji, staff=1)]),
                0
            ),
            # A message with a non-duck reaction from a non-staffer and staffer should return 0
            (
                "Non-duck reaction from staffer + non-staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.thumbs_up_emoji, staff=1, nonstaff=1)]),
                0
            ),
            # A message with a unicode duck reaction from a non-staffer should return 0
            (
                "Unicode Duck Reaction from non-staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.unicode_duck_emoji, nonstaff=1)]),
                0
            ),
            # A message with a unicode duck reaction from a staffer should return 1
            (
                "Unicode Duck Reaction from staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.unicode_duck_emoji, staff=1)]),
                1
            ),
            # A message with a unicode duck reaction from a non-staffer and staffer should return 1
            (
                "Unicode Duck Reaction from staffer + non-staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.unicode_duck_emoji, staff=1, nonstaff=1)]),
                1
            ),
            # A message with a duckpond duck reaction from a non-staffer should return 0
            (
                "Duckpond Duck Reaction from non-staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.duck_pond_emoji, nonstaff=1)]),
                0
            ),
            # A message with a duckpond duck reaction from a staffer should return 1
            (
                "Duckpond Duck Reaction from staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.duck_pond_emoji, staff=1)]),
                1
            ),
            # A message with a duckpond duck reaction from a non-staffer and staffer should return 1
            (
                "Duckpond Duck Reaction from staffer + non-staffer",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.duck_pond_emoji, staff=1, nonstaff=1)]),
                1
            ),

            # Complex test cases
            # A message with duckpond duck reactions from 3 staffers and 2 non-staffers returns 3
            (
                "Duckpond Duck Reaction from 3 staffers + 2 non-staffers",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=self.duck_pond_emoji, staff=3, nonstaff=2)]),
                3
            ),
            # A staffer with multiple duck reactions only counts once
            (
                "Two different duck reactions from the same staffer",
                helpers.MockMessage(
                    reactions=[
                        helpers.MockReaction(emoji=self.duck_pond_emoji, users=[self.staff_member]),
                        helpers.MockReaction(emoji=self.unicode_duck_emoji, users=[self.staff_member]),
                    ]
                ),
                1
            ),
            # A non-string emoji does not count (to test the `isinstance(reaction.emoji, str)` elif)
            (
                "Reaction with non-Emoji/str emoij from 3 staffers + 2 non-staffers",
                helpers.MockMessage(reactions=[self._get_reaction(emoji=100, staff=3, nonstaff=2)]),
                0
            ),
            # We correctly sum when multiple reactions are provided.
            (
                "Duckpond Duck Reaction from 3 staffers + 2 non-staffers",
                helpers.MockMessage(
                    reactions=[
                        self._get_reaction(emoji=self.duck_pond_emoji, staff=3, nonstaff=2),
                        self._get_reaction(emoji=self.unicode_duck_emoji, staff=4, nonstaff=9),
                    ]
                ),
                3 + 4
            ),
        )

        for description, message, expected_count in test_cases:
            actual_count = await self.cog.count_ducks(message)
            with self.subTest(test_case=description, expected_count=expected_count, actual_count=actual_count):
                self.assertEqual(expected_count, actual_count)

    async def test_relay_message_correctly_relays_content_and_attachments(self):
        """The `relay_message` method should correctly relay message content and attachments."""
        send_webhook_path = f"{MODULE_PATH}.send_webhook"
        send_attachments_path = f"{MODULE_PATH}.send_attachments"
        author = MagicMock(
            display_name="x",
            avatar_url="https://"
        )

        self.cog.webhook = helpers.MockAsyncWebhook()

        test_values = (
            (helpers.MockMessage(author=author, clean_content="", attachments=[]), False, False),
            (helpers.MockMessage(author=author, clean_content="message", attachments=[]), True, False),
            (helpers.MockMessage(author=author, clean_content="", attachments=["attachment"]), False, True),
            (helpers.MockMessage(author=author, clean_content="message", attachments=["attachment"]), True, True),
        )

        for message, expect_webhook_call, expect_attachment_call in test_values:
            with patch(send_webhook_path, new_callable=AsyncMock) as send_webhook:
                with patch(send_attachments_path, new_callable=AsyncMock) as send_attachments:
                    with self.subTest(clean_content=message.clean_content, attachments=message.attachments):
                        await self.cog.relay_message(message)

                        self.assertEqual(expect_webhook_call, send_webhook.called)
                        self.assertEqual(expect_attachment_call, send_attachments.called)

                        message.add_reaction.assert_called_once_with(self.checkmark_emoji)

    @patch(f"{MODULE_PATH}.send_attachments", new_callable=AsyncMock)
    async def test_relay_message_handles_irretrievable_attachment_exceptions(self, send_attachments):
        """The `relay_message` method should handle irretrievable attachments."""
        message = helpers.MockMessage(clean_content="message", attachments=["attachment"])
        side_effects = (discord.errors.Forbidden(MagicMock(), ""), discord.errors.NotFound(MagicMock(), ""))

        self.cog.webhook = helpers.MockAsyncWebhook()
        log = logging.getLogger("bot.exts.duck_pond")

        for side_effect in side_effects:  # pragma: no cover
            send_attachments.side_effect = side_effect
            with patch(f"{MODULE_PATH}.send_webhook", new_callable=AsyncMock) as send_webhook:
                with self.subTest(side_effect=type(side_effect).__name__):
                    with self.assertNotLogs(logger=log, level=logging.ERROR):
                        await self.cog.relay_message(message)

                    self.assertEqual(send_webhook.call_count, 2)

    @patch(f"{MODULE_PATH}.send_webhook", new_callable=AsyncMock)
    @patch(f"{MODULE_PATH}.send_attachments", new_callable=AsyncMock)
    async def test_relay_message_handles_attachment_http_error(self, send_attachments, send_webhook):
        """The `relay_message` method should handle irretrievable attachments."""
        message = helpers.MockMessage(clean_content="message", attachments=["attachment"])

        self.cog.webhook = helpers.MockAsyncWebhook()
        log = logging.getLogger("bot.exts.duck_pond")

        side_effect = discord.HTTPException(MagicMock(), "")
        send_attachments.side_effect = side_effect
        with self.subTest(side_effect=type(side_effect).__name__):
            with self.assertLogs(logger=log, level=logging.ERROR) as log_watcher:
                await self.cog.relay_message(message)

            send_webhook.assert_called_once_with(
                webhook=self.cog.webhook,
                content=message.clean_content,
                username=message.author.display_name,
                avatar_url=message.author.avatar_url
            )

            self.assertEqual(len(log_watcher.records), 1)

            record = log_watcher.records[0]
            self.assertEqual(record.levelno, logging.ERROR)

    def _mock_payload(self, label: str, is_custom_emoji: bool, id_: int, emoji_name: str):
        """Creates a mock `on_raw_reaction_add` payload with the specified emoji data."""
        payload = MagicMock(name=label)
        payload.emoji.is_custom_emoji.return_value = is_custom_emoji
        payload.emoji.id = id_
        payload.emoji.name = emoji_name
        return payload

    async def test_payload_has_duckpond_emoji_correctly_detects_relevant_emojis(self):
        """The `on_raw_reaction_add` event handler should ignore irrelevant emojis."""
        test_values = (
            # Custom Emojis
            (
                self._mock_payload(
                    label="Custom Duckpond Emoji",
                    is_custom_emoji=True,
                    id_=constants.DuckPond.custom_emojis[0],
                    emoji_name=""
                ),
                True
            ),
            (
                self._mock_payload(
                    label="Custom Non-Duckpond Emoji",
                    is_custom_emoji=True,
                    id_=123,
                    emoji_name=""
                ),
                False
            ),
            # Unicode Emojis
            (
                self._mock_payload(
                    label="Unicode Duck Emoji",
                    is_custom_emoji=False,
                    id_=1,
                    emoji_name=self.unicode_duck_emoji
                ),
                True
            ),
            (
                self._mock_payload(
                    label="Unicode Non-Duck Emoji",
                    is_custom_emoji=False,
                    id_=1,
                    emoji_name=self.thumbs_up_emoji
                ),
                False
            ),
        )

        for payload, expected_return in test_values:
            actual_return = self.cog._payload_has_duckpond_emoji(payload)
            with self.subTest(case=payload._mock_name, expected_return=expected_return, actual_return=actual_return):
                self.assertEqual(expected_return, actual_return)

    @patch(f"{MODULE_PATH}.discord.utils.get")
    @patch(f"{MODULE_PATH}.DuckPond._payload_has_duckpond_emoji", new=MagicMock(return_value=False))
    def test_on_raw_reaction_add_returns_early_with_payload_without_duck_emoji(self, utils_get):
        """The `on_raw_reaction_add` method should return early if the payload does not contain a duck emoji."""
        self.assertIsNone(asyncio.run(self.cog.on_raw_reaction_add(payload=MagicMock())))

        # Ensure we've returned before making an unnecessary API call in the lines of code after the emoji check
        utils_get.assert_not_called()

    def _raw_reaction_mocks(self, channel_id, message_id, user_id):
        """Sets up mocks for tests of the `on_raw_reaction_add` event listener."""
        channel = helpers.MockTextChannel(id=channel_id)
        self.bot.get_all_channels.return_value = (channel,)

        message = helpers.MockMessage(id=message_id)

        channel.fetch_message.return_value = message

        member = helpers.MockMember(id=user_id, roles=[self.staff_role])
        message.guild.members = (member,)

        payload = MagicMock(channel_id=channel_id, message_id=message_id, user_id=user_id)

        return channel, message, member, payload

    async def test_on_raw_reaction_add_returns_for_bot_and_non_staff_members(self):
        """The `on_raw_reaction_add` event handler should return for bot users or non-staff members."""
        channel_id = 1234
        message_id = 2345
        user_id = 3456

        channel, message, _, payload = self._raw_reaction_mocks(channel_id, message_id, user_id)

        test_cases = (
            ("non-staff member", helpers.MockMember(id=user_id)),
            ("bot staff member", helpers.MockMember(id=user_id, roles=[self.staff_role], bot=True)),
        )

        payload.emoji = self.duck_pond_emoji

        for description, member in test_cases:
            message.guild.members = (member, )
            with self.subTest(test_case=description), patch(f"{MODULE_PATH}.DuckPond.has_green_checkmark") as checkmark:
                checkmark.side_effect = AssertionError(
                    "Expected method to return before calling `self.has_green_checkmark`."
                )
                self.assertIsNone(await self.cog.on_raw_reaction_add(payload))

                # Check that we did make it past the payload checks
                channel.fetch_message.assert_called_once()
                channel.fetch_message.reset_mock()

    @patch(f"{MODULE_PATH}.DuckPond.is_staff")
    @patch(f"{MODULE_PATH}.DuckPond.count_ducks", new_callable=AsyncMock)
    def test_on_raw_reaction_add_returns_on_message_with_green_checkmark_placed_by_bot(self, count_ducks, is_staff):
        """The `on_raw_reaction_add` event should return when the message has a green check mark placed by the bot."""
        channel_id = 31415926535
        message_id = 27182818284
        user_id = 16180339887

        channel, message, member, payload = self._raw_reaction_mocks(channel_id, message_id, user_id)

        payload.emoji = helpers.MockPartialEmoji(name=self.unicode_duck_emoji)
        payload.emoji.is_custom_emoji.return_value = False

        message.reactions = [helpers.MockReaction(emoji=self.checkmark_emoji, users=[self.bot.user])]

        is_staff.return_value = True
        count_ducks.side_effect = AssertionError("Expected method to return before calling `self.count_ducks`")

        self.assertIsNone(asyncio.run(self.cog.on_raw_reaction_add(payload)))

        # Assert that we've made it past `self.is_staff`
        is_staff.assert_called_once()

    async def test_on_raw_reaction_add_does_not_relay_below_duck_threshold(self):
        """The `on_raw_reaction_add` listener should not relay messages or attachments below the duck threshold."""
        test_cases = (
            (constants.DuckPond.threshold - 1, False),
            (constants.DuckPond.threshold, True),
            (constants.DuckPond.threshold + 1, True),
        )

        channel, message, member, payload = self._raw_reaction_mocks(channel_id=3, message_id=4, user_id=5)

        payload.emoji = self.duck_pond_emoji

        for duck_count, should_relay in test_cases:
            with patch(f"{MODULE_PATH}.DuckPond.relay_message", new_callable=AsyncMock) as relay_message:
                with patch(f"{MODULE_PATH}.DuckPond.count_ducks", new_callable=AsyncMock) as count_ducks:
                    count_ducks.return_value = duck_count
                    with self.subTest(duck_count=duck_count, should_relay=should_relay):
                        await self.cog.on_raw_reaction_add(payload)

                        # Confirm that we've made it past counting
                        count_ducks.assert_called_once()

                        # Did we relay a message?
                        has_relayed = relay_message.called
                        self.assertEqual(has_relayed, should_relay)

                        if should_relay:
                            relay_message.assert_called_once_with(message)

    async def test_on_raw_reaction_remove_prevents_removal_of_green_checkmark_depending_on_the_duck_count(self):
        """The `on_raw_reaction_remove` listener prevents removal of the check mark on messages with enough ducks."""
        checkmark = helpers.MockPartialEmoji(name=self.checkmark_emoji)

        message = helpers.MockMessage(id=1234)

        channel = helpers.MockTextChannel(id=98765)
        channel.fetch_message.return_value = message

        self.bot.get_all_channels.return_value = (channel, )

        payload = MagicMock(channel_id=channel.id, message_id=message.id, emoji=checkmark)

        test_cases = (
            (constants.DuckPond.threshold - 1, False),
            (constants.DuckPond.threshold, True),
            (constants.DuckPond.threshold + 1, True),
        )
        for duck_count, should_re_add_checkmark in test_cases:
            with patch(f"{MODULE_PATH}.DuckPond.count_ducks", new_callable=AsyncMock) as count_ducks:
                count_ducks.return_value = duck_count
                with self.subTest(duck_count=duck_count, should_re_add_checkmark=should_re_add_checkmark):
                    await self.cog.on_raw_reaction_remove(payload)

                    # Check if we fetched the message
                    channel.fetch_message.assert_called_once_with(message.id)

                    # Check if we actually counted the number of ducks
                    count_ducks.assert_called_once_with(message)

                    has_re_added_checkmark = message.add_reaction.called
                    self.assertEqual(should_re_add_checkmark, has_re_added_checkmark)

                    if should_re_add_checkmark:
                        message.add_reaction.assert_called_once_with(self.checkmark_emoji)
                        message.add_reaction.reset_mock()

                    # reset mocks
                    channel.fetch_message.reset_mock()
                    message.reset_mock()

    def test_on_raw_reaction_remove_ignores_removal_of_non_checkmark_reactions(self):
        """The `on_raw_reaction_remove` listener should ignore the removal of non-check mark emojis."""
        channel = helpers.MockTextChannel(id=98765)

        channel.fetch_message.side_effect = AssertionError(
            "Expected method to return before calling `channel.fetch_message`"
        )

        self.bot.get_all_channels.return_value = (channel, )

        payload = MagicMock(emoji=helpers.MockPartialEmoji(name=self.thumbs_up_emoji), channel_id=channel.id)

        self.assertIsNone(asyncio.run(self.cog.on_raw_reaction_remove(payload)))

        channel.fetch_message.assert_not_called()


class DuckPondSetupTests(unittest.TestCase):
    """Tests setup of the `DuckPond` cog."""

    def test_setup(self):
        """Setup of the extension should call add_cog."""
        bot = helpers.MockBot()
        duck_pond.setup(bot)
        bot.add_cog.assert_called_once()
