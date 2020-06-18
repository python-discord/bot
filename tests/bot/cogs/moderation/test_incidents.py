import asyncio
import enum
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

import aiohttp
import discord

from bot.cogs.moderation import Incidents, incidents
from tests.helpers import (
    MockAsyncWebhook,
    MockBot,
    MockMember,
    MockMessage,
    MockReaction,
    MockRole,
    MockTextChannel,
    MockUser,
)


class MockSignal(enum.Enum):
    A = "A"
    B = "B"


mock_404 = discord.NotFound(
    response=MagicMock(aiohttp.ClientResponse),  # Mock the erroneous response
    message="Not found",
)


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


class TestMakeConfirmationTask(TestIncidents):
    """
    Tests for the `Incidents.make_confirmation_task` method.

    Writing tests for this method is difficult, as it mostly just delegates the provided
    information elsewhere. There is very little internal logic. Whether our approach
    works conceptually is difficult to prove using unit tests.
    """

    def test_make_confirmation_task_check(self):
        """
        The internal check will recognize the passed incident.

        This is a little tricky - we first pass a message with a specific `id` in, and then
        retrieve the built check from the `call_args` of the `wait_for` method. This relies
        on the check being passed as a kwarg.

        Once the check is retrieved, we assert that it gives True for our incident's `id`,
        and False for any other.

        If this function begins to fail, first check that `created_check` is being retrieved
        correctly. It should be the function that is built locally in the tested method.
        """
        self.cog_instance.make_confirmation_task(MockMessage(id=123))

        self.cog_instance.bot.wait_for.assert_called_once()
        created_check = self.cog_instance.bot.wait_for.call_args.kwargs["check"]

        # The `message_id` matches the `id` of our incident
        self.assertTrue(created_check(payload=MagicMock(message_id=123)))

        # This `message_id` does not match
        self.assertFalse(created_check(payload=MagicMock(message_id=0)))


@patch("bot.cogs.moderation.incidents.ALLOWED_ROLES", {1, 2})
@patch("bot.cogs.moderation.incidents.Incidents.make_confirmation_task", AsyncMock())  # Generic awaitable
class TestProcessEvent(TestIncidents):
    """Tests for the `Incidents.process_event` coroutine."""

    @patch("bot.cogs.moderation.incidents.ALLOWED_ROLES", {1, 2})
    async def test_process_event_bad_role(self):
        """The reaction is removed when the author lacks all allowed roles."""
        incident = MockMessage()
        member = MockMember(roles=[MockRole(id=0)])  # Must have role 1 or 2

        await self.cog_instance.process_event("reaction", incident, member)
        incident.remove_reaction.assert_called_once_with("reaction", member)

    async def test_process_event_bad_emoji(self):
        """
        The reaction is removed when an invalid emoji is used.

        This requires that we pass in a `member` with valid roles, as we need the role check
        to succeed.
        """
        incident = MockMessage()
        member = MockMember(roles=[MockRole(id=1)])  # Member has allowed role

        await self.cog_instance.process_event("invalid_signal", incident, member)
        incident.remove_reaction.assert_called_once_with("invalid_signal", member)

    async def test_process_event_no_archive_on_investigating(self):
        """Message is not archived on `Signal.INVESTIGATING`."""
        with patch("bot.cogs.moderation.incidents.Incidents.archive", AsyncMock()) as mocked_archive:
            await self.cog_instance.process_event(
                reaction=incidents.Signal.INVESTIGATING.value,
                incident=MockMessage(),
                member=MockMember(roles=[MockRole(id=1)]),
            )

        mocked_archive.assert_not_called()

    async def test_process_event_no_delete_if_archive_fails(self):
        """
        Original message is not deleted when `Incidents.archive` returns False.

        This is the way of signaling that the relay failed, and we should not remove the original,
        as that would result in losing the incident record.
        """
        incident = MockMessage()

        with patch("bot.cogs.moderation.incidents.Incidents.archive", AsyncMock(return_value=False)):
            await self.cog_instance.process_event(
                reaction=incidents.Signal.ACTIONED.value,
                incident=incident,
                member=MockMember(roles=[MockRole(id=1)])
            )

        incident.delete.assert_not_called()

    async def test_process_event_confirmation_task_is_awaited(self):
        """Task given by `Incidents.make_confirmation_task` is awaited before method exits."""
        mock_task = AsyncMock()

        with patch("bot.cogs.moderation.incidents.Incidents.make_confirmation_task", mock_task):
            await self.cog_instance.process_event(
                reaction=incidents.Signal.ACTIONED.value,
                incident=MockMessage(),
                member=MockMember(roles=[MockRole(id=1)])
            )

        mock_task.assert_awaited()

    async def test_process_event_confirmation_task_timeout_is_handled(self):
        """
        Confirmation task `asyncio.TimeoutError` is handled gracefully.

        We have `make_confirmation_task` return a mock with a side effect, and then catch the
        exception should it propagate out of `process_event`. This is so that we can then manually
        fail the test with a more informative message than just the plain traceback.
        """
        mock_task = AsyncMock(side_effect=asyncio.TimeoutError())

        try:
            with patch("bot.cogs.moderation.incidents.Incidents.make_confirmation_task", mock_task):
                await self.cog_instance.process_event(
                    reaction=incidents.Signal.ACTIONED.value,
                    incident=MockMessage(),
                    member=MockMember(roles=[MockRole(id=1)])
                )
        except asyncio.TimeoutError:
            self.fail("TimeoutError was not handled gracefully, and propagated out of `process_event`!")


class TestResolveMessage(TestIncidents):
    """Tests for the `Incidents.resolve_message` coroutine."""

    async def test_resolve_message_pass_message_id(self):
        """Method will call `_get_message` with the passed `message_id`."""
        await self.cog_instance.resolve_message(123)
        self.cog_instance.bot._connection._get_message.assert_called_once_with(123)

    async def test_resolve_message_in_cache(self):
        """
        No API call is made if the queried message exists in the cache.

        We mock the `_get_message` return value regardless of input. Whether it finds the message
        internally is considered d.py's responsibility, not ours.
        """
        cached_message = MockMessage(id=123)
        self.cog_instance.bot._connection._get_message = MagicMock(return_value=cached_message)

        return_value = await self.cog_instance.resolve_message(123)

        self.assertIs(return_value, cached_message)
        self.cog_instance.bot.get_channel.assert_not_called()  # The `fetch_message` line was never hit

    async def test_resolve_message_not_in_cache(self):
        """
        The message is retrieved from the API if it isn't cached.

        This is desired behaviour for messages which exist, but were sent before the bot's
        current session.
        """
        self.cog_instance.bot._connection._get_message = MagicMock(return_value=None)  # Cache returns None

        # API returns our message
        uncached_message = MockMessage()
        fetch_message = AsyncMock(return_value=uncached_message)
        self.cog_instance.bot.get_channel = MagicMock(return_value=MockTextChannel(fetch_message=fetch_message))

        retrieved_message = await self.cog_instance.resolve_message(123)
        self.assertIs(retrieved_message, uncached_message)

    async def test_resolve_message_doesnt_exist(self):
        """
        If the API returns a 404, the function handles it gracefully and returns None.

        This is an edge-case happening with racing events - event A will relay the message
        to the archive and delete the original. Once event B acquires the `event_lock`,
        it will not find the message in the cache, and will ask the API.
        """
        self.cog_instance.bot._connection._get_message = MagicMock(return_value=None)  # Cache returns None

        fetch_message = AsyncMock(side_effect=mock_404)
        self.cog_instance.bot.get_channel = MagicMock(return_value=MockTextChannel(fetch_message=fetch_message))

        self.assertIsNone(await self.cog_instance.resolve_message(123))

    async def test_resolve_message_fetch_fails(self):
        """
        Non-404 errors are handled, logged & None is returned.

        In contrast with a 404, this should make an error-level log. We assert that at least
        one such log was made - we do not make any assertions about the log's message.
        """
        self.cog_instance.bot._connection._get_message = MagicMock(return_value=None)  # Cache returns None

        arbitrary_error = discord.HTTPException(
            response=MagicMock(aiohttp.ClientResponse),
            message="Arbitrary error",
        )
        fetch_message = AsyncMock(side_effect=arbitrary_error)
        self.cog_instance.bot.get_channel = MagicMock(return_value=MockTextChannel(fetch_message=fetch_message))

        with self.assertLogs(logger=incidents.log, level=logging.ERROR):
            self.assertIsNone(await self.cog_instance.resolve_message(123))


class TestOnMessage(TestIncidents):
    """
    Tests for the `Incidents.on_message` listener.

    Notice the decorators mocking the `is_incident` return value. The `is_incidents`
    function is tested in `TestIsIncident` - here we do not worry about it.
    """

    @patch("bot.cogs.moderation.incidents.is_incident", MagicMock(return_value=True))
    async def test_on_message_incident(self):
        """Messages qualifying as incidents are passed to `add_signals`."""
        incident = MockMessage()

        with patch("bot.cogs.moderation.incidents.add_signals", AsyncMock()) as mock_add_signals:
            await self.cog_instance.on_message(incident)

        mock_add_signals.assert_called_once_with(incident)

    @patch("bot.cogs.moderation.incidents.is_incident", MagicMock(return_value=False))
    async def test_on_message_non_incident(self):
        """Messages not qualifying as incidents are ignored."""
        with patch("bot.cogs.moderation.incidents.add_signals", AsyncMock()) as mock_add_signals:
            await self.cog_instance.on_message(MockMessage())

        mock_add_signals.assert_not_called()
