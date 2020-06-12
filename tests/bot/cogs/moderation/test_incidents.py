import enum
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

import discord

from bot.cogs.moderation import incidents


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
        self.incident = MagicMock(
            discord.Message,
            channel=MagicMock(discord.TextChannel, id=123),
            content="this is an incident",
            author=MagicMock(discord.User, bot=False),
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
        self.incident.channel = MagicMock(discord.TextChannel, id=456)
        self.check_false()

    def test_is_incident_false_content(self):
        """Message doesn't qualify if content begins with hash symbol."""
        self.incident.content = "# this is a comment message"
        self.check_false()

    def test_is_incident_false_author(self):
        """Message doesn't qualify if author is a bot."""
        self.incident.author = MagicMock(discord.User, bot=True)
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
            MagicMock(discord.Reaction, emoji="A", me=True),
            MagicMock(discord.Reaction, emoji="B", me=True),
            MagicMock(discord.Reaction, emoji="C", me=False),
        )
        message = MagicMock(discord.Message, reactions=reactions)
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
        message = MagicMock(discord.Message)
        own_reactions = MagicMock(return_value={"A", "B"})

        with patch("bot.cogs.moderation.incidents.own_reactions", own_reactions):
            self.assertTrue(incidents.has_signals(message))

    def test_has_signals_false(self):
        """False when `own_reactions` does not return all emoji in `ALLOWED_EMOJI`."""
        message = MagicMock(discord.Message)
        own_reactions = MagicMock(return_value={"A", "C"})

        with patch("bot.cogs.moderation.incidents.own_reactions", own_reactions):
            self.assertFalse(incidents.has_signals(message))


class Signal(enum.Enum):
    A = "A"
    B = "B"


@patch("bot.cogs.moderation.incidents.Signal", Signal)
class TestAddSignals(unittest.IsolatedAsyncioTestCase):
    """
    Assertions for the `add_signals` coroutine.

    These are all fairly similar and could go into a single test function, but I found the
    patching & sub-testing fairly awkward in that case and decided to split them up
    to avoid unnecessary syntax noise.
    """

    def setUp(self):
        """Prepare a mock incident message for tests to use."""
        self.incident = MagicMock(discord.Message, add_reaction=AsyncMock())

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
