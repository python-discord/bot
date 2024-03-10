import asyncio
import datetime
import enum
import logging
import typing as t
import unittest
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import aiohttp
import discord

from bot.constants import Colours
from bot.exts.moderation import incidents
from bot.utils.messages import format_user
from bot.utils.time import TimestampFormats, discord_timestamp
from tests.base import RedisTestCase
from tests.helpers import (
    MockAsyncWebhook,
    MockAttachment,
    MockBot,
    MockMember,
    MockMessage,
    MockReaction,
    MockRole,
    MockTextChannel,
    MockUser,
    no_create_task,
)

CURRENT_TIME = datetime.datetime(2022, 1, 1, tzinfo=datetime.UTC)


class MockAsyncIterable:
    """
    Helper for mocking asynchronous for loops.

    It does not appear that the `unittest` library currently provides anything that would
    allow us to simply mock an async iterator, such as `discord.TextChannel.history`.

    We therefore write our own helper to wrap a regular synchronous iterable, and feed
    its values via `__anext__` rather than `__next__`.

    This class was written for the purposes of testing the `Incidents` cog - it may not
    be generic enough to be placed in the `tests.helpers` module.
    """

    def __init__(self, messages: t.Iterable):
        """Take a sync iterable to be wrapped."""
        self.iter_messages = iter(messages)

    def __aiter__(self):
        """Return `self` as we provide the `__anext__` method."""
        return self

    async def __anext__(self):
        """
        Feed the next item, or raise `StopAsyncIteration`.

        Since we're wrapping a sync iterator, it will communicate that it has been depleted
        by raising a `StopIteration`. The `async for` construct does not expect it, and we
        therefore need to substitute it for the appropriate exception type.
        """
        try:
            return next(self.iter_messages)
        except StopIteration:
            raise StopAsyncIteration


class MockSignal(enum.Enum):
    A = "A"
    B = "B"


mock_404 = discord.NotFound(
    response=MagicMock(aiohttp.ClientResponse),  # Mock the erroneous response
    message="Not found",
)


class TestDownloadFile(unittest.IsolatedAsyncioTestCase):
    """Collection of tests for the `download_file` helper function."""

    async def test_download_file_success(self):
        """If `to_file` succeeds, function returns the acquired `discord.File`."""
        file = MagicMock(discord.File, filename="bigbadlemon.jpg")
        attachment = MockAttachment(to_file=AsyncMock(return_value=file))

        acquired_file = await incidents.download_file(attachment)
        self.assertIs(file, acquired_file)

    async def test_download_file_404(self):
        """If `to_file` encounters a 404, function handles the exception & returns None."""
        attachment = MockAttachment(to_file=AsyncMock(side_effect=mock_404))

        acquired_file = await incidents.download_file(attachment)
        self.assertIsNone(acquired_file)

    async def test_download_file_fail(self):
        """If `to_file` fails on a non-404 error, function logs the exception & returns None."""
        arbitrary_error = discord.HTTPException(MagicMock(aiohttp.ClientResponse), "Arbitrary API error")
        attachment = MockAttachment(to_file=AsyncMock(side_effect=arbitrary_error))

        with self.assertLogs(logger=incidents.log, level=logging.ERROR):
            acquired_file = await incidents.download_file(attachment)

        self.assertIsNone(acquired_file)


class TestMakeEmbed(unittest.IsolatedAsyncioTestCase):
    """Collection of tests for the `make_embed` helper function."""

    async def test_make_embed_actioned(self):
        """Embed is coloured green and footer contains 'Actioned' when `outcome=Signal.ACTIONED`."""
        embed, file = await incidents.make_embed(
            incident=MockMessage(created_at=CURRENT_TIME),
            outcome=incidents.Signal.ACTIONED,
            actioned_by=MockMember()
        )

        self.assertEqual(embed.colour.value, Colours.soft_green)
        self.assertIn("Actioned", embed.footer.text)

    async def test_make_embed_not_actioned(self):
        """Embed is coloured red and footer contains 'Rejected' when `outcome=Signal.NOT_ACTIONED`."""
        embed, file = await incidents.make_embed(
            incident=MockMessage(created_at=CURRENT_TIME),
            outcome=incidents.Signal.NOT_ACTIONED,
            actioned_by=MockMember()
        )

        self.assertEqual(embed.colour.value, Colours.soft_red)
        self.assertIn("Rejected", embed.footer.text)

    async def test_make_embed_content(self):
        """Incident content appears as embed description."""
        incident = MockMessage(content="this is an incident", created_at=CURRENT_TIME)

        reported_timestamp = discord_timestamp(CURRENT_TIME)
        relative_timestamp = discord_timestamp(CURRENT_TIME, TimestampFormats.RELATIVE)

        embed, file = await incidents.make_embed(incident, incidents.Signal.ACTIONED, MockMember())

        self.assertEqual(
            f"{incident.content}\n\n*Reported {reported_timestamp} ({relative_timestamp}).*",
            embed.description
        )

    async def test_make_embed_with_attachment_succeeds(self):
        """Incident's attachment is downloaded and displayed in the embed's image field."""
        file = MagicMock(discord.File, filename="bigbadjoe.jpg")
        attachment = MockAttachment(filename="bigbadjoe.jpg")
        incident = MockMessage(content="this is an incident", attachments=[attachment], created_at=CURRENT_TIME)

        # Patch `download_file` to return our `file`
        with patch("bot.exts.moderation.incidents.download_file", AsyncMock(return_value=file)):
            embed, returned_file = await incidents.make_embed(incident, incidents.Signal.ACTIONED, MockMember())

        self.assertIs(file, returned_file)
        self.assertEqual("attachment://bigbadjoe.jpg", embed.image.url)

    async def test_make_embed_with_attachment_fails(self):
        """Incident's attachment fails to download, proxy url is linked instead."""
        attachment = MockAttachment(proxy_url="discord.com/bigbadjoe.jpg")
        incident = MockMessage(content="this is an incident", attachments=[attachment], created_at=CURRENT_TIME)

        # Patch `download_file` to return None as if the download failed
        with patch("bot.exts.moderation.incidents.download_file", AsyncMock(return_value=None)):
            embed, returned_file = await incidents.make_embed(incident, incidents.Signal.ACTIONED, MockMember())

        self.assertIsNone(returned_file)

        # The author name field is simply expected to have something in it, we do not assert the message
        self.assertGreater(len(embed.author.name), 0)
        self.assertEqual(embed.author.url, "discord.com/bigbadjoe.jpg")  # However, it should link the exact url


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
            reference=None,
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


@patch("bot.exts.moderation.incidents.ALL_SIGNALS", {"A", "B"})
class TestHasSignals(unittest.TestCase):
    """
    Assertions for the `has_signals` function.

    We patch `ALL_SIGNALS` globally. Each test function then patches `own_reactions`
    as appropriate.
    """

    def test_has_signals_true(self):
        """True when `own_reactions` returns all emoji in `ALL_SIGNALS`."""
        message = MockMessage()
        own_reactions = MagicMock(return_value={"A", "B"})

        with patch("bot.exts.moderation.incidents.own_reactions", own_reactions):
            self.assertTrue(incidents.has_signals(message))

    def test_has_signals_false(self):
        """False when `own_reactions` does not return all emoji in `ALL_SIGNALS`."""
        message = MockMessage()
        own_reactions = MagicMock(return_value={"A", "C"})

        with patch("bot.exts.moderation.incidents.own_reactions", own_reactions):
            self.assertFalse(incidents.has_signals(message))


@patch("bot.exts.moderation.incidents.Signal", MockSignal)
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

    @patch("bot.exts.moderation.incidents.own_reactions", MagicMock(return_value=set()))
    async def test_add_signals_missing(self):
        """All emoji are added when none are present."""
        await incidents.add_signals(self.incident)
        self.incident.add_reaction.assert_has_calls([call("A"), call("B")])

    @patch("bot.exts.moderation.incidents.own_reactions", MagicMock(return_value={"A"}))
    async def test_add_signals_partial(self):
        """Only missing emoji are added when some are present."""
        await incidents.add_signals(self.incident)
        self.incident.add_reaction.assert_has_calls([call("B")])

    @patch("bot.exts.moderation.incidents.own_reactions", MagicMock(return_value={"A", "B"}))
    async def test_add_signals_present(self):
        """No emoji are added when all are present."""
        await incidents.add_signals(self.incident)
        self.incident.add_reaction.assert_not_called()


class TestIncidents(RedisTestCase):
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
        with no_create_task():
            self.cog_instance = incidents.Incidents(MockBot())


@patch("asyncio.sleep", AsyncMock())  # Prevent the coro from sleeping to speed up the test
class TestCrawlIncidents(TestIncidents):
    """
    Tests for the `Incidents.crawl_incidents` coroutine.

    Apart from `test_crawl_incidents_waits_until_cache_ready`, all tests in this class
    will patch the return values of `is_incident` and `has_signal` and then observe
    whether the `AsyncMock` for `add_signals` was awaited or not.

    The `add_signals` mock is added by each test separately to ensure it is clean (has not
    been awaited by another test yet). The mock can be reset, but this appears to be the
    cleaner way.

    For each test, we inject a mock channel with a history of 1 message only (see: `setUp`).
    """

    def setUp(self):
        """For each test, ensure `bot.get_channel` returns a channel with 1 arbitrary message."""
        super().setUp()  # First ensure we get `cog_instance` from parent

        incidents_history = MagicMock(return_value=MockAsyncIterable([MockMessage()]))
        self.cog_instance.bot.get_channel = MagicMock(return_value=MockTextChannel(history=incidents_history))

    async def test_crawl_incidents_waits_until_cache_ready(self):
        """
        The coroutine will await the `wait_until_guild_available` event.

        Since this task is schedule in the `__init__`, it is critical that it waits for the
        cache to be ready, so that it can safely get the #incidents channel.
        """
        await self.cog_instance.crawl_incidents()
        self.cog_instance.bot.wait_until_guild_available.assert_awaited()

    @patch("bot.exts.moderation.incidents.add_signals", AsyncMock())
    @patch("bot.exts.moderation.incidents.is_incident", MagicMock(return_value=False))  # Message doesn't qualify
    @patch("bot.exts.moderation.incidents.has_signals", MagicMock(return_value=False))
    async def test_crawl_incidents_noop_if_is_not_incident(self):
        """Signals are not added for a non-incident message."""
        await self.cog_instance.crawl_incidents()
        incidents.add_signals.assert_not_awaited()

    @patch("bot.exts.moderation.incidents.add_signals", AsyncMock())
    @patch("bot.exts.moderation.incidents.is_incident", MagicMock(return_value=True))  # Message qualifies
    @patch("bot.exts.moderation.incidents.has_signals", MagicMock(return_value=True))  # But already has signals
    async def test_crawl_incidents_noop_if_message_already_has_signals(self):
        """Signals are not added for messages which already have them."""
        await self.cog_instance.crawl_incidents()
        incidents.add_signals.assert_not_awaited()

    @patch("bot.exts.moderation.incidents.add_signals", AsyncMock())
    @patch("bot.exts.moderation.incidents.is_incident", MagicMock(return_value=True))  # Message qualifies
    @patch("bot.exts.moderation.incidents.has_signals", MagicMock(return_value=False))  # And doesn't have signals
    async def test_crawl_incidents_add_signals_called(self):
        """Message has signals added as it does not have them yet and qualifies as an incident."""
        await self.cog_instance.crawl_incidents()
        incidents.add_signals.assert_awaited_once()


class TestArchive(TestIncidents):
    """Tests for the `Incidents.archive` coroutine."""
    async def test_archive_webhook_not_found(self):
        """
        Method recovers and returns False when the webhook is not found.

        Implicitly, this also tests that the error is handled internally and doesn't
        propagate out of the method, which is just as important.
        """
        self.cog_instance.bot.fetch_webhook = AsyncMock(side_effect=mock_404)
        self.assertFalse(
            await self.cog_instance.archive(
                incident=MockMessage(created_at=CURRENT_TIME),
                outcome=MagicMock(),
                actioned_by=MockMember()
            )
        )

    async def test_archive_relays_incident(self):
        """
        If webhook is found, method relays `incident` properly.

        This test will assert that the fetched webhook's `send` method is fed the correct arguments,
        and that the `archive` method returns True.
        """
        webhook = MockAsyncWebhook()
        self.cog_instance.bot.fetch_webhook = AsyncMock(return_value=webhook)  # Patch in our webhook

        # Define our own `incident` to be archived
        incident = MockMessage(
            content="this is an incident",
            author=MockUser(display_name="author_name", display_avatar=Mock(url="author_avatar")),
            id=123,
        )
        built_embed = MagicMock(discord.Embed, id=123)  # We patch `make_embed` to return this

        with patch("bot.exts.moderation.incidents.make_embed", AsyncMock(return_value=(built_embed, None))):
            archive_return = await self.cog_instance.archive(incident, MagicMock(value="A"), MockMember())

        # Now we check that the webhook was given the correct args, and that `archive` returned True
        webhook.send.assert_called_once_with(
            embed=built_embed,
            username="author_name",
            avatar_url="author_avatar",
            file=None,
        )
        self.assertTrue(archive_return)

    async def test_archive_clyde_username(self):
        """
        The archive webhook username is cleansed using `sub_clyde`.

        Discord will reject any webhook with "clyde" in the username field, as it impersonates
        the official Clyde bot. Since we do not control what the username will be (the incident
        author name is used), we must ensure the name is cleansed, otherwise the relay may fail.

        This test assumes the username is passed as a kwarg. If this test fails, please review
        whether the passed argument is being retrieved correctly.
        """
        webhook = MockAsyncWebhook()
        self.cog_instance.bot.fetch_webhook = AsyncMock(return_value=webhook)

        message_from_clyde = MockMessage(author=MockUser(display_name="clyde the great"), created_at=CURRENT_TIME)
        await self.cog_instance.archive(message_from_clyde, MagicMock(incidents.Signal), MockMember())

        self.assertNotIn("clyde", webhook.send.call_args.kwargs["username"])


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
        with no_create_task():
            self.cog_instance.make_confirmation_task(MockMessage(id=123))

        self.cog_instance.bot.wait_for.assert_called_once()
        created_check = self.cog_instance.bot.wait_for.call_args.kwargs["check"]

        # The `message_id` matches the `id` of our incident
        self.assertTrue(created_check(payload=MagicMock(message_id=123)))

        # This `message_id` does not match
        self.assertFalse(created_check(payload=MagicMock(message_id=0)))


@patch("bot.exts.moderation.incidents.ALLOWED_ROLES", {1, 2})
@patch("bot.exts.moderation.incidents.Incidents.make_confirmation_task", AsyncMock())  # Generic awaitable
class TestProcessEvent(TestIncidents):
    """Tests for the `Incidents.process_event` coroutine."""

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
        with patch("bot.exts.moderation.incidents.Incidents.archive", AsyncMock()) as mocked_archive:
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

        with patch("bot.exts.moderation.incidents.Incidents.archive", AsyncMock(return_value=False)):
            await self.cog_instance.process_event(
                reaction=incidents.Signal.ACTIONED.value,
                incident=incident,
                member=MockMember(roles=[MockRole(id=1)])
            )

        incident.delete.assert_not_called()

    async def test_process_event_confirmation_task_is_awaited(self):
        """Task given by `Incidents.make_confirmation_task` is awaited before method exits."""
        mock_task = AsyncMock()
        mock_member = MockMember(display_name="Bobby Johnson", roles=[MockRole(id=1)])

        with patch("bot.exts.moderation.incidents.Incidents.make_confirmation_task", mock_task):
            await self.cog_instance.process_event(
                reaction=incidents.Signal.ACTIONED.value,
                incident=MockMessage(author=mock_member, id=123, created_at=CURRENT_TIME),
                member=mock_member
            )

        mock_task.assert_awaited()

    async def test_process_event_confirmation_task_timeout_is_handled(self):
        """
        Confirmation task `asyncio.TimeoutError` is handled gracefully.

        We have `make_confirmation_task` return a mock with a side effect, and then catch the
        exception should it propagate out of `process_event`. This is so that we can then manually
        fail the test with a more informative message than just the plain traceback.
        """
        mock_task = AsyncMock(side_effect=TimeoutError())

        try:
            with patch("bot.exts.moderation.incidents.Incidents.make_confirmation_task", mock_task):
                await self.cog_instance.process_event(
                    reaction=incidents.Signal.ACTIONED.value,
                    incident=MockMessage(id=123, created_at=CURRENT_TIME),
                    member=MockMember(roles=[MockRole(id=1)])
                )
        except TimeoutError:
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


@patch("bot.constants.Channels.incidents", 123)
class TestOnRawReactionAdd(TestIncidents):
    """
    Tests for the `Incidents.on_raw_reaction_add` listener.

    Writing tests for this listener comes with additional complexity due to the listener
    awaiting the `crawl_task` task. See `asyncSetUp` for further details, which attempts
    to make unit testing this function possible.
    """

    def setUp(self):
        """
        Prepare & assign `payload` attribute.

        This attribute represents an *ideal* payload which will not be rejected by the
        listener. As each test will receive a fresh instance, it can be mutated to
        observe how the listener's behaviour changes with different attributes on
        the passed payload.
        """
        super().setUp()  # Ensure `cog_instance` is assigned

        self.payload = MagicMock(
            discord.RawReactionActionEvent,
            channel_id=123,  # Patched at class level
            message_id=456,
            member=MockMember(bot=False),
            emoji="reaction",
        )

    async def asyncSetUp(self):
        """
        Prepare an empty task and assign it as `crawl_task`.

        It appears that the `unittest` framework does not provide anything for mocking
        asyncio tasks. An `AsyncMock` instance can be called and then awaited, however,
        it does not provide the `done` method or any other parts of the `asyncio.Task`
        interface.

        Although we do not need to make any assertions about the task itself while
        testing the listener, the code will still await it and call the `done` method,
        and so we must inject something that will not fail on either action.

        Note that this is done in an `asyncSetUp`, which runs after `setUp`.
        The justification is that creating an actual task requires the event
        loop to be ready, which is not the case in the `setUp`.
        """
        mock_task = asyncio.create_task(AsyncMock()())  # Mock async func, then a coro
        self.cog_instance.crawl_task = mock_task

    async def test_on_raw_reaction_add_wrong_channel(self):
        """
        Events outside of #incidents will be ignored.

        We check this by asserting that `resolve_message` was never queried.
        """
        self.payload.channel_id = 0
        self.cog_instance.resolve_message = AsyncMock()

        await self.cog_instance.on_raw_reaction_add(self.payload)
        self.cog_instance.resolve_message.assert_not_called()

    async def test_on_raw_reaction_add_user_is_bot(self):
        """
        Events dispatched by bot accounts will be ignored.

        We check this by asserting that `resolve_message` was never queried.
        """
        self.payload.member = MockMember(bot=True)
        self.cog_instance.resolve_message = AsyncMock()

        await self.cog_instance.on_raw_reaction_add(self.payload)
        self.cog_instance.resolve_message.assert_not_called()

    async def test_on_raw_reaction_add_message_doesnt_exist(self):
        """
        Listener gracefully handles the case where `resolve_message` gives None.

        We check this by asserting that `process_event` was never called.
        """
        self.cog_instance.process_event = AsyncMock()
        self.cog_instance.resolve_message = AsyncMock(return_value=None)

        await self.cog_instance.on_raw_reaction_add(self.payload)
        self.cog_instance.process_event.assert_not_called()

    async def test_on_raw_reaction_add_message_is_not_an_incident(self):
        """
        The event won't be processed if the related message is not an incident.

        This is an edge-case that can happen if someone manually leaves a reaction
        on a pinned message, or a comment.

        We check this by asserting that `process_event` was never called.
        """
        self.cog_instance.process_event = AsyncMock()
        self.cog_instance.resolve_message = AsyncMock(return_value=MockMessage())

        with patch("bot.exts.moderation.incidents.is_incident", MagicMock(return_value=False)):
            await self.cog_instance.on_raw_reaction_add(self.payload)

        self.cog_instance.process_event.assert_not_called()

    async def test_on_raw_reaction_add_valid_event_is_processed(self):
        """
        If the reaction event is valid, it is passed to `process_event`.

        This is the case when everything goes right:
            * The reaction was placed in #incidents, and not by a bot
            * The message was found successfully
            * The message qualifies as an incident

        Additionally, we check that all arguments were passed as expected.
        """
        incident = MockMessage(id=1)

        self.cog_instance.process_event = AsyncMock()
        self.cog_instance.resolve_message = AsyncMock(return_value=incident)

        with patch("bot.exts.moderation.incidents.is_incident", MagicMock(return_value=True)):
            await self.cog_instance.on_raw_reaction_add(self.payload)

        self.cog_instance.process_event.assert_called_with(
            "reaction",  # Defined in `self.payload`
            incident,
            self.payload.member,
        )


class TestOnMessage(TestIncidents):
    """
    Tests for the `Incidents.on_message` listener.

    Notice the decorators mocking the `is_incident` return value. The `is_incidents`
    function is tested in `TestIsIncident` - here we do not worry about it.
    """

    @patch("bot.exts.moderation.incidents.is_incident", MagicMock(return_value=True))
    async def test_on_message_incident(self):
        """Messages qualifying as incidents are passed to `add_signals`."""
        incident = MockMessage()

        with patch("bot.exts.moderation.incidents.add_signals", AsyncMock()) as mock_add_signals:
            await self.cog_instance.on_message(incident)

        mock_add_signals.assert_called_once_with(incident)

    @patch("bot.exts.moderation.incidents.is_incident", MagicMock(return_value=False))
    async def test_on_message_non_incident(self):
        """Messages not qualifying as incidents are ignored."""
        with patch("bot.exts.moderation.incidents.add_signals", AsyncMock()) as mock_add_signals:
            await self.cog_instance.on_message(MockMessage())

        mock_add_signals.assert_not_called()


class TestMessageLinkEmbeds(TestIncidents):
    """Tests for `extract_message_links` coroutine."""

    async def test_shorten_text(self):
        """Test all cases of text shortening by mocking messages."""
        tests = {
            "thisisasingleword"*10: "thisisasinglewordthisisasinglewordthisisasinglewor...",

            "\n".join("Lets make a new line test".split()): "Lets\nmake\na...",

            "Hello, World!" * 300: (
                "Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!"
                "Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!"
                "Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!"
                "Hello, World!Hello, World!H..."
            )
        }

        for content, expected_conversion in tests.items():
            with self.subTest(content=content, expected_conversion=expected_conversion):
                conversion = incidents.shorten_text(content)
                self.assertEqual(conversion, expected_conversion)

    async def extract_and_form_message_link_embeds(self):
        """
        Extract message links from a mocked message and form the message link embed.

        Considers all types of message links, discord supports.
        """
        self.guild_id_patcher = mock.patch("bot.exts.backend.sync._cog.constants.Guild.id", 5)
        self.guild_id = self.guild_id_patcher.start()

        msg = MockMessage(id=555, content="Hello, World!" * 3000)
        msg.channel.mention = "#lemonade-stand"

        msg_links = [
            # Valid Message links
            f"https://discord.com/channels/{self.guild_id}/{msg.channel.discord_id}/{msg.discord_id}",
            f"http://canary.discord.com/channels/{self.guild_id}/{msg.channel.discord_id}/{msg.discord_id}",

            # Invalid Message links
            f"https://discord.com/channels/{msg.channel.discord_id}/{msg.discord_id}",
            f"https://discord.com/channels/{self.guild_id}/{msg.channel.discord_id}000/{msg.discord_id}",
        ]

        incident_msg = MockMessage(
            id=777,
            content=(
                f"I would like to report the following messages, "
                f"as they break our rules: \n{', '.join(msg_links)}"
            )
        )

        with patch(
                "bot.exts.moderation.incidents.Incidents.extract_message_links", AsyncMock()
        ) as mock_extract_message_links:
            embeds = mock_extract_message_links(incident_msg)
            description = (
                f"**Author:** {format_user(msg.author)}\n"
                f"**Channel:** {msg.channel.mention} ({msg.channel.category}/#{msg.channel.name})\n"
                f"**Content:** {('Hello, World!' * 3000)[:300] + '...'}\n"
            )

            # Check number of embeds returned with number of valid links
            self.assertEqual(len(embeds), 2)

            # Check for the embed descriptions
            for embed in embeds:
                self.assertEqual(embed.description, description)
