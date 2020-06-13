import enum
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

import aiohttp
import discord

from bot.cogs.moderation import Incidents, incidents
from tests.helpers import MockAsyncWebhook, MockBot, MockMessage, MockReaction, MockTextChannel, MockUser


class MockSignal(enum.Enum):
    A = "A"
    B = "B"


@patch("bot.constants.Channels.incidents", 123)
class TestIsIncident(unittest.TestCase):
    """
    Collection of tests for the `is_incident` helper function.

    In `setUp`, we will create a mock message which should qualify as an incident. Each
    test case will then mutate this instance to make it **not** qualify, in various ways.

    Notice that we patch the #incidents channel id globally for this class.
    """

    def setUp(self) -> None:
        """Prepare a mock message which should qualify as an incident."""
        self.incident = MockMessage(
            channel=MockTextChannel(id=123),
            content="this is an incident",
            author=MockUser(bot=False),
            pinned=False,
        )

    def test_is_incident_true(self):
        """Message qualifies as an incident if unchanged."""
        self.assertTrue(incidents.is_incident(self.incident))

    def check_false(self):
        """Assert that `self.incident` does **not** qualify as an incident."""
        self.assertFalse(incidents.is_incident(self.incident))

    def test_is_incident_false_channel(self):
        """Message doesn't qualify if sent outside of #incidents."""
        self.incident.channel = MockTextChannel(id=456)
        self.check_false()

    def test_is_incident_false_content(self):
        """Message doesn't qualify if content begins with hash symbol."""
        self.incident.content = "# this is a comment message"
        self.check_false()

    def test_is_incident_false_author(self):
        """Message doesn't qualify if author is a bot."""
        self.incident.author = MockUser(bot=True)
        self.check_false()

    def test_is_incident_false_pinned(self):
        """Message doesn't qualify if it is pinned."""
        self.incident.pinned = True
        self.check_false()


class TestOwnReactions(unittest.TestCase):
    """Assertions for the `own_reactions` function."""

    def test_own_reactions(self):
        """Only bot's own emoji are extracted from the input incident."""
        reactions = (
            MockReaction(emoji="A", me=True),
            MockReaction(emoji="B", me=True),
            MockReaction(emoji="C", me=False),
        )
        message = MockMessage(reactions=reactions)
        self.assertSetEqual(incidents.own_reactions(message), {"A", "B"})


@patch("bot.cogs.moderation.incidents.ALLOWED_EMOJI", {"A", "B"})
class TestHasSignals(unittest.TestCase):
    """
    Assertions for the `has_signals` function.

    We patch `ALLOWED_EMOJI` globally. Each test function then patches `own_reactions`
    as appropriate.
    """

    def test_has_signals_true(self):
        """True when `own_reactions` returns all emoji in `ALLOWED_EMOJI`."""
        message = MockMessage()
        own_reactions = MagicMock(return_value={"A", "B"})

        with patch("bot.cogs.moderation.incidents.own_reactions", own_reactions):
            self.assertTrue(incidents.has_signals(message))

    def test_has_signals_false(self):
        """False when `own_reactions` does not return all emoji in `ALLOWED_EMOJI`."""
        message = MockMessage()
        own_reactions = MagicMock(return_value={"A", "C"})

        with patch("bot.cogs.moderation.incidents.own_reactions", own_reactions):
            self.assertFalse(incidents.has_signals(message))


@patch("bot.cogs.moderation.incidents.Signal", MockSignal)
class TestAddSignals(unittest.IsolatedAsyncioTestCase):
    """
    Assertions for the `add_signals` coroutine.

    These are all fairly similar and could go into a single test function, but I found the
    patching & sub-testing fairly awkward in that case and decided to split them up
    to avoid unnecessary syntax noise.
    """

    def setUp(self):
        """Prepare a mock incident message for tests to use."""
        self.incident = MockMessage()

    @patch("bot.cogs.moderation.incidents.own_reactions", MagicMock(return_value=set()))
    async def test_add_signals_missing(self):
        """All emoji are added when none are present."""
        await incidents.add_signals(self.incident)
        self.incident.add_reaction.assert_has_calls([call("A"), call("B")])

    @patch("bot.cogs.moderation.incidents.own_reactions", MagicMock(return_value={"A"}))
    async def test_add_signals_partial(self):
        """Only missing emoji are added when some are present."""
        await incidents.add_signals(self.incident)
        self.incident.add_reaction.assert_has_calls([call("B")])

    @patch("bot.cogs.moderation.incidents.own_reactions", MagicMock(return_value={"A", "B"}))
    async def test_add_signals_present(self):
        """No emoji are added when all are present."""
        await incidents.add_signals(self.incident)
        self.incident.add_reaction.assert_not_called()


class TestIncidents(unittest.IsolatedAsyncioTestCase):
    """
    Tests for bound methods of the `Incidents` cog.

    Use this as a base class for `Incidents` tests - it will prepare a fresh instance
    for each test function, but not make any assertions on its own. Tests can mutate
    the instance as they wish.
    """

    def setUp(self):
        """
        Prepare a fresh `Incidents` instance for each test.

        Note that this will not schedule `crawl_incidents` in the background, as everything
        is being mocked. The `crawl_task` attribute will end up being None.
        """
        self.cog_instance = Incidents(MockBot())


class TestArchive(TestIncidents):
    """Tests for the `Incidents.archive` coroutine."""

    async def test_archive_webhook_not_found(self):
        """
        Method recovers and returns False when the webhook is not found.

        Implicitly, this also tests that the error is handled internally and doesn't
        propagate out of the method, which is just as important.
        """
        mock_404 = discord.NotFound(
            response=MagicMock(aiohttp.ClientResponse),  # Mock the erroneous response
            message="Webhook not found",
        )

        self.cog_instance.bot.fetch_webhook = AsyncMock(side_effect=mock_404)
        self.assertFalse(await self.cog_instance.archive(incident=MockMessage(), outcome=MagicMock()))

    async def test_archive_relays_incident(self):
        """
        If webhook is found, method relays `incident` properly.

        This test will assert the following:
            * The fetched webhook's `send` method is fed the correct arguments
            * The message returned by `send` will have `outcome` reaction added
            * Finally, the `archive` method returns True

        Assertions are made specifically in this order.
        """
        webhook_message = MockMessage()  # The message that will be returned by the webhook's `send` method
        webhook = MockAsyncWebhook(send=AsyncMock(return_value=webhook_message))

        self.cog_instance.bot.fetch_webhook = AsyncMock(return_value=webhook)  # Patch in our webhook

        # Now we'll pas our own `incident` to `archive` and capture the return value
        incident = MockMessage(
            clean_content="pingless message",
            content="pingful message",
            author=MockUser(name="author_name", avatar_url="author_avatar"),
            id=123,
        )
        archive_return = await self.cog_instance.archive(incident, outcome=MagicMock(value="A"))

        # Check that the webhook was dispatched correctly
        webhook.send.assert_called_once_with(
            content="pingless message",
            username="author_name",
            avatar_url="author_avatar",
            wait=True,
        )

        # Now check that the correct emoji was added to the relayed message
        webhook_message.add_reaction.assert_called_once_with("A")

        # Finally check that the method returned True
        self.assertTrue(archive_return)
