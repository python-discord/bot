import itertools
import unittest
from datetime import UTC, datetime
from unittest import mock
from unittest.mock import AsyncMock, Mock

from discord import PermissionOverwrite

from bot.constants import Channels, Guild, MODERATION_ROLES, Roles
from bot.exts.moderation import silence
from tests.base import RedisTestCase
from tests.helpers import (
    MockBot,
    MockContext,
    MockGuild,
    MockMember,
    MockRole,
    MockTextChannel,
    MockVoiceChannel,
    autospec,
)


# Have to subclass it because builtins can't be patched.
class PatchedDatetime(datetime):
    """A datetime object with a mocked now() function."""

    now = mock.create_autospec(datetime, "now")


class SilenceTest(RedisTestCase):
    """A base class for Silence tests that correctly sets up the cog and redis."""

    @autospec(silence, "Scheduler", pass_mocks=False)
    @autospec(silence.Silence, "_reschedule", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot(get_channel=lambda _id: MockTextChannel(id=_id))
        self.cog = silence.Silence(self.bot)

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await self.cog.cog_load()  # Populate instance attributes.


class SilenceNotifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.alert_channel = MockTextChannel()
        self.notifier = silence.SilenceNotifier(self.alert_channel)
        self.notifier.stop = self.notifier_stop_mock = Mock()
        self.notifier.start = self.notifier_start_mock = Mock()

    def test_add_channel_adds_channel(self):
        """Channel is added to `_silenced_channels` with the current loop."""
        channel = Mock()
        self.notifier.add_channel(channel)
        self.assertDictEqual(self.notifier._silenced_channels, {channel: self.notifier._current_loop})

    def test_add_channel_loop_called_correctly(self):
        """Loop is called only in correct scenarios."""

        # Loop is started if `_silenced_channels` was empty.
        self.notifier.add_channel(Mock())
        self.notifier_start_mock.assert_called_once()

        self.notifier_start_mock.reset_mock()

        # Loop start is not called when `_silenced_channels` is not empty.
        self.notifier.add_channel(Mock())
        self.notifier_start_mock.assert_not_called()

    def test_remove_channel_removes_channel(self):
        """Channel is removed from `_silenced_channels`."""
        channel = Mock()
        self.notifier.add_channel(channel)
        self.notifier.remove_channel(channel)
        self.assertDictEqual(self.notifier._silenced_channels, {})

    def test_remove_channel_stops_loop(self):
        """Notifier loop is stopped if `_silenced_channels` is empty after remove."""
        channel = Mock()
        self.notifier.add_channel(channel)
        self.notifier_stop_mock.assert_not_called()

        self.notifier.remove_channel(channel)
        self.notifier_stop_mock.assert_called_once()

    def test_remove_channel_skips_stop_with_channels(self):
        """Notifier loop is not stopped if `_silenced_channels` is not empty after remove."""
        self.notifier.remove_channel(Mock())
        self.notifier_stop_mock.assert_not_called()

    async def test_notifier_private_sends_alert(self):
        """Alert is sent on 15 min intervals."""
        test_cases = (900, 1800, 2700)
        for current_loop in test_cases:
            with self.subTest(current_loop=current_loop):
                with mock.patch.object(self.notifier, "_current_loop", new=current_loop):
                    await self.notifier._notifier()
                self.alert_channel.send.assert_called_once_with(
                    f"<@&{Roles.moderators}> currently silenced channels: "
                )
            self.alert_channel.send.reset_mock()

    async def test_notifier_skips_alert(self):
        """Alert is skipped on first loop or not an increment of 900."""
        test_cases = (0, 15, 5000)
        for current_loop in test_cases:
            with (
                self.subTest(current_loop=current_loop),
                mock.patch.object(self.notifier, "_current_loop", new=current_loop),
            ):
                await self.notifier._notifier()
                self.alert_channel.send.assert_not_called()


class SilenceCogTests(SilenceTest):
    """Tests for the general functionality of the Silence cog."""

    async def test_cog_load_got_guild(self):
        """Bot got guild after it became available."""
        self.bot.wait_until_guild_available.assert_awaited_once()
        self.bot.get_guild.assert_called_once_with(Guild.id)

    async def test_cog_load_got_channels(self):
        """Got channels from bot."""
        self.assertEqual(self.cog._mod_alerts_channel.id, Channels.mod_alerts)

    async def test_cog_load_got_notifier(self):
        """Notifier was started with channel."""
        with mock.patch.object(silence, "SilenceNotifier") as notifier:
            await self.cog.cog_load()
        notifier.assert_called_once_with(MockTextChannel(id=Channels.mod_log))
        self.assertEqual(self.cog.notifier, notifier.return_value)

    async def testcog_load_rescheduled(self):
        """`_reschedule_` coroutine was awaited."""
        self.cog._reschedule = AsyncMock()
        await self.cog.cog_load()
        self.cog._reschedule.assert_awaited_once_with()

    @autospec("discord.ext.commands", "has_any_role")
    @mock.patch.object(silence.constants, "MODERATION_ROLES", new=(1, 2, 3))
    async def test_cog_check(self, role_check):
        """Role check was called with `MODERATION_ROLES`"""
        ctx = MockContext()
        role_check.return_value.predicate = mock.AsyncMock()

        await self.cog.cog_check(ctx)
        role_check.assert_called_once_with(*(1, 2, 3))
        role_check.return_value.predicate.assert_awaited_once_with(ctx)

    async def test_force_voice_sync(self):
        """Tests the _force_voice_sync helper function."""
        await self.cog.cog_load()

        # Create a regular member, and one member for each of the moderation roles
        moderation_members = [MockMember(roles=[MockRole(id=role)]) for role in MODERATION_ROLES]
        members = [MockMember(), *moderation_members]

        channel = MockVoiceChannel(members=members)

        await self.cog._force_voice_sync(channel)
        for member in members:
            if member in moderation_members:
                member.move_to.assert_not_called()
            else:
                self.assertEqual(member.move_to.call_count, 2)
                calls = member.move_to.call_args_list

                # Tests that the member was moved to the afk channel, and back.
                self.assertEqual((channel.guild.afk_channel,), calls[0].args)
                self.assertEqual((channel,), calls[1].args)

    async def test_force_voice_sync_no_channel(self):
        """Test to ensure _force_voice_sync can create its own voice channel if one is not available."""
        await self.cog.cog_load()

        channel = MockVoiceChannel(guild=MockGuild(afk_channel=None))
        new_channel = MockVoiceChannel(delete=AsyncMock())
        channel.guild.create_voice_channel.return_value = new_channel

        await self.cog._force_voice_sync(channel)

        # Check channel creation
        overwrites = {
            channel.guild.default_role: PermissionOverwrite(speak=False, connect=False, view_channel=False)
        }
        channel.guild.create_voice_channel.assert_awaited_once_with("mute-temp", overwrites=overwrites)

        # Check bot deleted channel
        new_channel.delete.assert_awaited_once()

    async def test_voice_kick(self):
        """Test to ensure kick function can remove all members from a voice channel."""
        await self.cog.cog_load()

        # Create a regular member, and one member for each of the moderation roles
        moderation_members = [MockMember(roles=[MockRole(id=role)]) for role in MODERATION_ROLES]
        members = [MockMember(), *moderation_members]

        channel = MockVoiceChannel(members=members)
        await self.cog._kick_voice_members(channel)

        for member in members:
            if member in moderation_members:
                member.move_to.assert_not_called()
            else:
                self.assertEqual((None,), member.move_to.call_args_list[0].args)

    @staticmethod
    def create_erroneous_members() -> tuple[list[MockMember], list[MockMember]]:
        """
        Helper method to generate a list of members that error out on move_to call.

        Returns the list of erroneous members,
        as well as a list of regular and erroneous members combined, in that order.
        """
        erroneous_member = MockMember(move_to=AsyncMock(side_effect=Exception()))
        members = [MockMember(), erroneous_member]

        return erroneous_member, members

    async def test_kick_move_to_error(self):
        """Test to ensure move_to gets called on all members during kick, even if some fail."""
        await self.cog.cog_load()
        _, members = self.create_erroneous_members()

        await self.cog._kick_voice_members(MockVoiceChannel(members=members))
        for member in members:
            member.move_to.assert_awaited_once()

    async def test_sync_move_to_error(self):
        """Test to ensure move_to gets called on all members during sync, even if some fail."""
        await self.cog.cog_load()
        failing_member, members = self.create_erroneous_members()

        await self.cog._force_voice_sync(MockVoiceChannel(members=members))
        for member in members:
            self.assertEqual(member.move_to.call_count, 1 if member == failing_member else 2)


class SilenceArgumentParserTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the silence argument parser utility function."""

    @autospec(silence.Silence, "send_message", pass_mocks=False)
    @autospec(silence.Silence, "_set_silence_overwrites", return_value=False, pass_mocks=False)
    @autospec(silence.Silence, "parse_silence_args")
    async def test_command(self, parser_mock):
        """Test that the command passes in the correct arguments for different calls."""
        bot = MockBot()
        cog = silence.Silence(bot)

        test_cases = (
            (),
            (15, ),
            (MockTextChannel(),),
            (MockTextChannel(), 15),
        )

        ctx = MockContext()
        parser_mock.return_value = (ctx.channel, 10)

        for case in test_cases:
            with self.subTest("Test command converters", args=case):
                await cog.silence.callback(cog, ctx, *case)

                try:
                    first_arg = case[0]
                except IndexError:
                    # Default value when the first argument is not passed
                    first_arg = None

                try:
                    second_arg = case[1]
                except IndexError:
                    # Default value when the second argument is not passed
                    second_arg = 10

                parser_mock.assert_called_with(ctx, first_arg, second_arg)

    async def test_no_arguments(self):
        """Test the parser when no arguments are passed to the command."""
        ctx = MockContext()
        channel, duration = silence.Silence.parse_silence_args(ctx, None, 10)

        self.assertEqual(ctx.channel, channel)
        self.assertEqual(10, duration)

    async def test_channel_only(self):
        """Test the parser when just the channel argument is passed."""
        expected_channel = MockTextChannel()
        actual_channel, duration = silence.Silence.parse_silence_args(MockContext(), expected_channel, 10)

        self.assertEqual(expected_channel, actual_channel)
        self.assertEqual(10, duration)

    async def test_duration_only(self):
        """Test the parser when just the duration argument is passed."""
        ctx = MockContext()
        channel, duration = silence.Silence.parse_silence_args(ctx, 15, 10)

        self.assertEqual(ctx.channel, channel)
        self.assertEqual(15, duration)

    async def test_all_args(self):
        """Test the parser when both channel and duration are passed."""
        expected_channel = MockTextChannel()
        actual_channel, duration = silence.Silence.parse_silence_args(MockContext(), expected_channel, 15)

        self.assertEqual(expected_channel, actual_channel)
        self.assertEqual(15, duration)


class RescheduleTests(RedisTestCase):
    """Tests for the rescheduling of cached unsilences."""

    @autospec(silence, "Scheduler", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = silence.Silence(self.bot)
        self.cog._unsilence_wrapper = mock.create_autospec(self.cog._unsilence_wrapper)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await self.cog.cog_load()  # Populate instance attributes.

    async def test_skipped_missing_channel(self):
        """Did nothing because the channel couldn't be retrieved."""
        await self.cog.unsilence_timestamps.set(123, -1)
        self.bot.get_channel.return_value = None

        await self.cog._reschedule()

        self.cog.notifier.add_channel.assert_not_called()
        self.cog._unsilence_wrapper.assert_not_called()
        self.cog.scheduler.schedule_later.assert_not_called()

    async def test_added_permanent_to_notifier(self):
        """Permanently silenced channels were added to the notifier."""
        channels = [MockTextChannel(id=123), MockTextChannel(id=456)]
        self.bot.get_channel.side_effect = channels
        await self.cog.unsilence_timestamps.set(123, -1)
        await self.cog.unsilence_timestamps.set(456, -1)
        await self.cog._reschedule()

        self.cog.notifier.add_channel.assert_any_call(channels[0])
        self.cog.notifier.add_channel.assert_any_call(channels[1])

        self.cog._unsilence_wrapper.assert_not_called()
        self.cog.scheduler.schedule_later.assert_not_called()

    async def test_unsilenced_expired(self):
        """Unsilenced expired silences."""
        channels = [MockTextChannel(id=123), MockTextChannel(id=456)]
        self.bot.get_channel.side_effect = channels
        await self.cog.unsilence_timestamps.set(123, 100)
        await self.cog.unsilence_timestamps.set(456, 200)

        await self.cog._reschedule()

        self.cog._unsilence_wrapper.assert_any_call(channels[0])
        self.cog._unsilence_wrapper.assert_any_call(channels[1])

        self.cog.notifier.add_channel.assert_not_called()
        self.cog.scheduler.schedule_later.assert_not_called()

    @mock.patch.object(silence, "datetime", new=PatchedDatetime)
    async def test_rescheduled_active(self):
        """Rescheduled active silences."""
        channels = [MockTextChannel(id=123), MockTextChannel(id=456)]
        self.bot.get_channel.side_effect = channels
        await self.cog.unsilence_timestamps.set(123, 2000)
        await self.cog.unsilence_timestamps.set(456, 3000)
        silence.datetime.now.return_value = datetime.fromtimestamp(1000, tz=UTC)

        self.cog._unsilence_wrapper = mock.MagicMock()
        unsilence_return = self.cog._unsilence_wrapper.return_value

        await self.cog._reschedule()

        # Yuck.
        calls = [mock.call(1000, 123, unsilence_return), mock.call(2000, 456, unsilence_return)]
        self.cog.scheduler.schedule_later.assert_has_calls(calls)

        unsilence_calls = [mock.call(channel) for channel in channels]
        self.cog._unsilence_wrapper.assert_has_calls(unsilence_calls)

        self.cog.notifier.add_channel.assert_not_called()


def voice_sync_helper(function):
    """Helper wrapper to test the sync and kick functions for voice channels."""
    @autospec(silence.Silence, "_force_voice_sync", "_kick_voice_members", "_set_silence_overwrites")
    async def inner(self, sync, kick, overwrites):
        overwrites.return_value = True
        await function(self, MockContext(), sync, kick)

    return inner


class SilenceTests(SilenceTest):
    """Tests for the silence command and its related helper methods."""

    def setUp(self) -> None:
        super().setUp()

        # Avoid unawaited coroutine warnings.
        self.cog.scheduler.schedule_later.side_effect = lambda delay, task_id, coro: coro.close()
        self.text_channel = MockTextChannel()
        self.text_overwrite = PermissionOverwrite(
            send_messages=True,
            add_reactions=False,
            create_private_threads=True,
            create_public_threads=False,
            send_messages_in_threads=True
        )
        self.text_channel.overwrites_for.return_value = self.text_overwrite

        self.voice_channel = MockVoiceChannel()
        self.voice_overwrite = PermissionOverwrite(connect=True, speak=True)
        self.voice_channel.overwrites_for.return_value = self.voice_overwrite

    async def test_sent_correct_message(self):
        """Appropriate failure/success message was sent by the command to the correct channel."""
        # The following test tuples are made up of:
        # duration, expected message, and the success of the _set_silence_overwrites function
        test_cases = (
            (0.0001, silence.MSG_SILENCE_SUCCESS.format(duration=0.0001), True,),
            (None, silence.MSG_SILENCE_PERMANENT, True,),
            (5, silence.MSG_SILENCE_FAIL, False,),
        )

        targets = (MockTextChannel(), MockVoiceChannel(), None)

        for (duration, message, was_silenced), target in itertools.product(test_cases, targets):
            with (
                mock.patch.object(self.cog, "_set_silence_overwrites", return_value=was_silenced),
                self.subTest(was_silenced=was_silenced, target=target, message=message),
                mock.patch.object(self.cog, "send_message") as send_message
            ):
                ctx = MockContext()
                await self.cog.silence.callback(self.cog, ctx, target, duration)
                send_message.assert_called_once_with(
                    message,
                    ctx.channel,
                    target or ctx.channel,
                    alert_target=was_silenced
                )

    @voice_sync_helper
    async def test_sync_called(self, ctx, sync, kick):
        """Tests if silence command calls sync on a voice channel."""
        channel = MockVoiceChannel()
        await self.cog.silence.callback(self.cog, ctx, channel, 10, kick=False)

        sync.assert_awaited_once_with(self.cog, channel)
        kick.assert_not_called()

    @voice_sync_helper
    async def test_kick_called(self, ctx, sync, kick):
        """Tests if silence command calls kick on a voice channel."""
        channel = MockVoiceChannel()
        await self.cog.silence.callback(self.cog, ctx, channel, 10, kick=True)

        kick.assert_awaited_once_with(channel)
        sync.assert_not_called()

    @voice_sync_helper
    async def test_sync_not_called(self, ctx, sync, kick):
        """Tests that silence command does not call sync on a text channel."""
        channel = MockTextChannel()
        await self.cog.silence.callback(self.cog, ctx, channel, 10, kick=False)

        sync.assert_not_called()
        kick.assert_not_called()

    @voice_sync_helper
    async def test_kick_not_called(self, ctx, sync, kick):
        """Tests that silence command does not call kick on a text channel."""
        channel = MockTextChannel()
        await self.cog.silence.callback(self.cog, ctx, channel, 10, kick=True)

        sync.assert_not_called()
        kick.assert_not_called()

    async def test_skipped_already_silenced(self):
        """Permissions were not set and `False` was returned for an already silenced channel."""
        subtests = (
            (
                False,
                MockTextChannel(),
                PermissionOverwrite(
                    send_messages=False,
                    add_reactions=False,
                    create_private_threads=False,
                    create_public_threads=False,
                    send_messages_in_threads=False
                )
            ),
            (
                True,
                MockTextChannel(),
                PermissionOverwrite(
                    send_messages=True,
                    add_reactions=True,
                    create_private_threads=True,
                    create_public_threads=True,
                    send_messages_in_threads=True
                )
            ),
            (
                True,
                MockTextChannel(),
                PermissionOverwrite(
                    send_messages=False,
                    add_reactions=False,
                    create_private_threads=False,
                    create_public_threads=False,
                    send_messages_in_threads=False
                )
            ),
            (False, MockVoiceChannel(), PermissionOverwrite(connect=False, speak=False)),
            (True, MockVoiceChannel(), PermissionOverwrite(connect=True, speak=True)),
            (True, MockVoiceChannel(), PermissionOverwrite(connect=False, speak=False)),
        )

        for contains, channel, overwrite in subtests:
            with self.subTest(contains=contains, is_text=isinstance(channel, MockTextChannel), overwrite=overwrite):
                self.cog.scheduler.__contains__.return_value = contains
                channel.overwrites_for.return_value = overwrite

                self.assertFalse(await self.cog._set_silence_overwrites(channel))
                channel.set_permissions.assert_not_called()

    async def test_silenced_text_channel(self):
        """Channel had `send_message` and `add_reactions` permissions revoked for verified role."""
        self.assertTrue(await self.cog._set_silence_overwrites(self.text_channel))
        self.assertFalse(self.text_overwrite.send_messages)
        self.assertFalse(self.text_overwrite.add_reactions)
        self.text_channel.set_permissions.assert_awaited_once_with(
            self.cog._everyone_role,
            overwrite=self.text_overwrite
        )

    async def test_silenced_voice_channel_speak(self):
        """Channel had `speak` permissions revoked for verified role."""
        self.assertTrue(await self.cog._set_silence_overwrites(self.voice_channel))
        self.assertFalse(self.voice_overwrite.speak)
        self.voice_channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_voice_role,
            overwrite=self.voice_overwrite
        )

    async def test_silenced_voice_channel_full(self):
        """Channel had `speak` and `connect` permissions revoked for verified role."""
        self.assertTrue(await self.cog._set_silence_overwrites(self.voice_channel, kick=True))
        self.assertFalse(self.voice_overwrite.speak or self.voice_overwrite.connect)
        self.voice_channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_voice_role,
            overwrite=self.voice_overwrite
        )

    async def test_preserved_other_overwrites_text(self):
        """Channel's other unrelated overwrites were not changed for a text channel mute."""
        prev_overwrite_dict = dict(self.text_overwrite)
        await self.cog._set_silence_overwrites(self.text_channel)
        new_overwrite_dict = dict(self.text_overwrite)

        # Remove related permission keys because they were changed by the method.
        for perm_name in (
                "send_messages",
                "add_reactions",
                "create_private_threads",
                "create_public_threads",
                "send_messages_in_threads"
        ):
            del prev_overwrite_dict[perm_name]
            del new_overwrite_dict[perm_name]

        self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)

    async def test_preserved_other_overwrites_voice(self):
        """Channel's other unrelated overwrites were not changed for a voice channel mute."""
        prev_overwrite_dict = dict(self.voice_overwrite)
        await self.cog._set_silence_overwrites(self.voice_channel)
        new_overwrite_dict = dict(self.voice_overwrite)

        # Remove 'connect' & 'speak' keys because they were changed by the method.
        del prev_overwrite_dict["connect"]
        del prev_overwrite_dict["speak"]
        del new_overwrite_dict["connect"]
        del new_overwrite_dict["speak"]

        self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)

    async def test_temp_not_added_to_notifier(self):
        """Channel was not added to notifier if a duration was set for the silence."""
        with (
            mock.patch.object(self.cog, "_set_silence_overwrites", return_value=True),
            mock.patch.object(self.cog.notifier, "add_channel")
        ):
            await self.cog.silence.callback(self.cog, MockContext(), 15)
            self.cog.notifier.add_channel.assert_not_called()

    async def test_indefinite_added_to_notifier(self):
        """Channel was added to notifier if a duration was not set for the silence."""
        with (
            mock.patch.object(self.cog, "_set_silence_overwrites", return_value=True),
            mock.patch.object(self.cog.notifier, "add_channel")
        ):
            await self.cog.silence.callback(self.cog, MockContext(), None, None)
            self.cog.notifier.add_channel.assert_called_once()

    async def test_silenced_not_added_to_notifier(self):
        """Channel was not added to the notifier if it was already silenced."""
        with (
            mock.patch.object(self.cog, "_set_silence_overwrites", return_value=False),
            mock.patch.object(self.cog.notifier, "add_channel")
        ):
            await self.cog.silence.callback(self.cog, MockContext(), 15)
            self.cog.notifier.add_channel.assert_not_called()

    async def test_cached_previous_overwrites(self):
        """Channel's previous overwrites were cached."""
        overwrite_json = (
            '{"send_messages": true, "add_reactions": false, "create_private_threads": true, '
            '"create_public_threads": false, "send_messages_in_threads": true}'
        )
        await self.cog._set_silence_overwrites(self.text_channel)
        self.assertEqual(await self.cog.previous_overwrites.get(self.text_channel.id), overwrite_json)

    @autospec(silence, "datetime")
    async def test_cached_unsilence_time(self, datetime_mock):
        """The UTC POSIX timestamp for the unsilence was cached."""
        now_timestamp = 100
        duration = 15
        timestamp = now_timestamp + duration * 60
        datetime_mock.now.return_value = datetime.fromtimestamp(now_timestamp, tz=UTC)

        ctx = MockContext(channel=self.text_channel)
        await self.cog.silence.callback(self.cog, ctx, duration)

        self.assertEqual(await self.cog.unsilence_timestamps.get(ctx.channel.id), timestamp)
        datetime_mock.now.assert_called_once_with(tz=UTC)  # Ensure it's using an aware dt.

    async def test_cached_indefinite_time(self):
        """A value of -1 was cached for a permanent silence."""
        ctx = MockContext(channel=self.text_channel)
        await self.cog.silence.callback(self.cog, ctx, None, None)
        self.assertEqual(await self.cog.unsilence_timestamps.get(ctx.channel.id), -1)

    async def test_scheduled_task(self):
        """An unsilence task was scheduled."""
        ctx = MockContext(channel=self.text_channel, invoke=mock.MagicMock())

        await self.cog.silence.callback(self.cog, ctx, 5)

        args = (300, ctx.channel.id, ctx.invoke.return_value)
        self.cog.scheduler.schedule_later.assert_called_once_with(*args)
        ctx.invoke.assert_called_once_with(self.cog.unsilence, channel=ctx.channel)

    async def test_permanent_not_scheduled(self):
        """A task was not scheduled for a permanent silence."""
        ctx = MockContext(channel=self.text_channel)
        await self.cog.silence.callback(self.cog, ctx, None, None)
        self.cog.scheduler.schedule_later.assert_not_called()

    async def test_indefinite_silence(self):
        """Test silencing a channel forever."""
        with mock.patch.object(self.cog, "_schedule_unsilence") as unsilence:
            ctx = MockContext(channel=self.text_channel)
            await self.cog.silence.callback(self.cog, ctx, -1)
            unsilence.assert_awaited_once_with(ctx, ctx.channel, None)


class UnsilenceTests(SilenceTest):
    """Tests for the unsilence command and its related helper methods."""

    def setUp(self) -> None:
        super().setUp()

        self.cog.scheduler.__contains__.return_value = True
        self.text_channel = MockTextChannel()
        self.text_overwrite = PermissionOverwrite(send_messages=False, add_reactions=False)
        self.text_channel.overwrites_for.return_value = self.text_overwrite

        self.voice_channel = MockVoiceChannel()
        self.voice_overwrite = PermissionOverwrite(connect=True, speak=True)
        self.voice_channel.overwrites_for.return_value = self.voice_overwrite

    async def test_sent_correct_message(self):
        """Appropriate failure/success message was sent by the command."""
        unsilenced_overwrite = PermissionOverwrite(send_messages=True, add_reactions=True)
        test_cases = (
            (True, silence.MSG_UNSILENCE_SUCCESS, unsilenced_overwrite),
            (False, silence.MSG_UNSILENCE_FAIL, unsilenced_overwrite),
            (False, silence.MSG_UNSILENCE_MANUAL, self.text_overwrite),
            (False, silence.MSG_UNSILENCE_MANUAL, PermissionOverwrite(send_messages=False)),
            (False, silence.MSG_UNSILENCE_MANUAL, PermissionOverwrite(add_reactions=False)),
        )

        targets = (None, MockTextChannel())

        for (was_unsilenced, message, overwrite), target in itertools.product(test_cases, targets):
            ctx = MockContext()
            ctx.channel.overwrites_for.return_value = overwrite
            if target:
                target.overwrites_for.return_value = overwrite

            with (
                mock.patch.object(self.cog, "_unsilence", return_value=was_unsilenced),
                mock.patch.object(self.cog, "send_message") as send_message,
                self.subTest(was_unsilenced=was_unsilenced, overwrite=overwrite, target=target),
            ):
                await self.cog.unsilence.callback(self.cog, ctx, channel=target)

                call_args = (message, ctx.channel, target or ctx.channel)
                send_message.assert_awaited_once_with(*call_args, alert_target=was_unsilenced)

    async def test_skipped_already_unsilenced(self):
        """Permissions were not set and `False` was returned for an already unsilenced channel."""
        self.cog.scheduler.__contains__.return_value = False

        for channel in (MockVoiceChannel(), MockTextChannel()):
            with self.subTest(channel=channel):
                self.assertFalse(await self.cog._unsilence(channel))
                channel.set_permissions.assert_not_called()

    async def test_restored_overwrites_text(self):
        """Text channel's `send_message` and `add_reactions` overwrites were restored."""
        await self.cog.previous_overwrites.set(self.text_channel.id, '{"send_messages": true, "add_reactions": false}')
        await self.cog._unsilence(self.text_channel)
        self.text_channel.set_permissions.assert_awaited_once_with(
            self.cog._everyone_role,
            overwrite=self.text_overwrite,
        )

        # Recall that these values are determined by the fixture.
        self.assertTrue(self.text_overwrite.send_messages)
        self.assertFalse(self.text_overwrite.add_reactions)

    async def test_restored_overwrites_voice(self):
        """Voice channel's `connect` and `speak` overwrites were restored."""
        await self.cog.previous_overwrites.set(self.voice_channel.id, '{"connect": true, "speak": true}')
        await self.cog._unsilence(self.voice_channel)
        self.voice_channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_voice_role,
            overwrite=self.voice_overwrite,
        )

        self.assertTrue(self.voice_overwrite.connect)
        self.assertTrue(self.voice_overwrite.speak)

    async def test_cache_miss_used_default_overwrites_text(self):
        """Text overwrites were set to None due previous values not being found in the cache."""

        await self.cog._unsilence(self.text_channel)
        self.text_channel.set_permissions.assert_awaited_once_with(
            self.cog._everyone_role,
            overwrite=self.text_overwrite,
        )

        self.assertIsNone(self.text_overwrite.send_messages)
        self.assertIsNone(self.text_overwrite.add_reactions)

    async def test_cache_miss_used_default_overwrites_voice(self):
        """Voice overwrites were set to None due previous values not being found in the cache."""

        await self.cog._unsilence(self.voice_channel)
        self.voice_channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_voice_role,
            overwrite=self.voice_overwrite,
        )

        self.assertIsNone(self.voice_overwrite.connect)
        self.assertIsNone(self.voice_overwrite.speak)

    async def test_cache_miss_sent_mod_alert_text(self):
        """A message was sent to the mod alerts channel upon muting a text channel."""
        await self.cog._unsilence(self.text_channel)
        self.cog._mod_alerts_channel.send.assert_awaited_once()

    async def test_cache_miss_sent_mod_alert_voice(self):
        """A message was sent to the mod alerts channel upon muting a voice channel."""
        await self.cog._unsilence(MockVoiceChannel())
        self.cog._mod_alerts_channel.send.assert_awaited_once()

    async def test_removed_notifier(self):
        """Channel was removed from `notifier`."""
        with mock.patch.object(silence.SilenceNotifier, "remove_channel"):
            await self.cog._unsilence(self.text_channel)
            self.cog.notifier.remove_channel.assert_called_once_with(self.text_channel)

    async def test_deleted_cached_overwrite(self):
        """Channel was deleted from the overwrites cache."""
        await self.cog.previous_overwrites.set(self.text_channel.id, '{"send_messages": true, "add_reactions": false}')
        await self.cog._unsilence(self.text_channel)
        self.assertEqual(await self.cog.previous_overwrites.get(self.text_channel.id), None)

    async def test_deleted_cached_time(self):
        """Channel was deleted from the timestamp cache."""
        await self.cog.unsilence_timestamps.set(self.text_channel.id, 100)
        await self.cog._unsilence(self.text_channel)
        self.assertEqual(await self.cog.unsilence_timestamps.get(self.text_channel.id), None)

    async def test_cancelled_task(self):
        """The scheduled unsilence task should be cancelled."""
        await self.cog._unsilence(self.text_channel)
        self.cog.scheduler.cancel.assert_called_once_with(self.text_channel.id)

    async def test_preserved_other_overwrites_text(self):
        """Text channel's other unrelated overwrites were not changed, including cache misses."""
        for overwrite_json in ('{"send_messages": true, "add_reactions": null}', None):
            with self.subTest(overwrite_json=overwrite_json):
                if overwrite_json is None:
                    await self.cog.previous_overwrites.delete(self.text_channel.id)
                else:
                    await self.cog.previous_overwrites.set(self.text_channel.id, overwrite_json)

                prev_overwrite_dict = dict(self.text_overwrite)
                await self.cog._unsilence(self.text_channel)
                new_overwrite_dict = dict(self.text_overwrite)

                # Remove these keys because they were modified by the unsilence.
                del prev_overwrite_dict["send_messages"]
                del prev_overwrite_dict["add_reactions"]
                del new_overwrite_dict["send_messages"]
                del new_overwrite_dict["add_reactions"]

                self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)

    async def test_preserved_other_overwrites_voice(self):
        """Voice channel's other unrelated overwrites were not changed, including cache misses."""
        for overwrite_json in ('{"connect": true, "speak": true}', None):
            with self.subTest(overwrite_json=overwrite_json):
                if overwrite_json is None:
                    await self.cog.previous_overwrites.delete(self.voice_channel.id)
                else:
                    await self.cog.previous_overwrites.set(self.voice_channel.id, overwrite_json)

                prev_overwrite_dict = dict(self.voice_overwrite)
                await self.cog._unsilence(self.voice_channel)
                new_overwrite_dict = dict(self.voice_overwrite)

                # Remove these keys because they were modified by the unsilence.
                del prev_overwrite_dict["connect"]
                del prev_overwrite_dict["speak"]
                del new_overwrite_dict["connect"]
                del new_overwrite_dict["speak"]

                self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)

    async def test_unsilence_role(self):
        """Tests unsilence_wrapper applies permission to the correct role."""
        test_cases = (
            (MockTextChannel(), self.cog.bot.get_guild(Guild.id).default_role),
            (MockVoiceChannel(), self.cog.bot.get_guild(Guild.id).get_role(Roles.voice_verified))
        )

        for channel, role in test_cases:
            with self.subTest(channel=channel, role=role):
                await self.cog._unsilence_wrapper(channel, MockContext())
                channel.overwrites_for.assert_called_with(role)


class SendMessageTests(unittest.IsolatedAsyncioTestCase):
    """Unittests for the send message helper function."""

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = silence.Silence(self.bot)

        self.text_channels = [MockTextChannel() for _ in range(2)]
        self.bot.get_channel.return_value = self.text_channels[1]

        self.voice_channel = MockVoiceChannel()

    async def test_send_to_channel(self):
        """Tests a basic case for the send function."""
        message = "Test basic message."
        await self.cog.send_message(message, *self.text_channels, alert_target=False)

        self.text_channels[0].send.assert_awaited_once_with(message)
        self.text_channels[1].send.assert_not_called()

    async def test_send_to_multiple_channels(self):
        """Tests sending messages to two channels."""
        message = "Test basic message."
        await self.cog.send_message(message, *self.text_channels, alert_target=True)

        self.text_channels[0].send.assert_awaited_once_with(message)
        self.text_channels[1].send.assert_awaited_once_with(message)

    async def test_duration_replacement(self):
        """Tests that the channel name was set correctly for one target channel."""
        message = "Current. The following should be replaced: {channel}."
        await self.cog.send_message(message, *self.text_channels, alert_target=False)

        updated_message = message.format(channel=self.text_channels[0].mention)
        self.text_channels[0].send.assert_awaited_once_with(updated_message)
        self.text_channels[1].send.assert_not_called()

    async def test_name_replacement_multiple_channels(self):
        """Tests that the channel name was set correctly for two channels."""
        message = "Current. The following should be replaced: {channel}."
        await self.cog.send_message(message, *self.text_channels, alert_target=True)

        self.text_channels[0].send.assert_awaited_once_with(message.format(channel=self.text_channels[0].mention))
        self.text_channels[1].send.assert_awaited_once_with(message.format(channel="current channel"))

    async def test_silence_voice(self):
        """Tests that the correct message was sent when a voice channel is muted without alerting."""
        message = "This should show up just here."
        await self.cog.send_message(message, self.text_channels[0], self.voice_channel, alert_target=False)
        self.text_channels[0].send.assert_awaited_once_with(message)
        self.text_channels[1].send.assert_not_called()

    async def test_silence_voice_alert(self):
        """Tests that the correct message was sent when a voice channel is muted with alerts."""
        with unittest.mock.patch.object(silence, "VOICE_CHANNELS") as mock_voice_channels:
            mock_voice_channels.get.return_value = self.text_channels[1].id

            message = "This should show up as {channel}."
            await self.cog.send_message(message, self.text_channels[0], self.voice_channel, alert_target=True)

        updated_message = message.format(channel=self.voice_channel.mention)
        self.text_channels[0].send.assert_awaited_once_with(updated_message)
        self.text_channels[1].send.assert_awaited_once_with(updated_message)

        mock_voice_channels.get.assert_called_once_with(self.voice_channel.id)

    async def test_silence_voice_sibling_channel(self):
        """Tests silencing a voice channel from the related text channel."""
        with unittest.mock.patch.object(silence, "VOICE_CHANNELS") as mock_voice_channels:
            mock_voice_channels.get.return_value = self.text_channels[1].id

            message = "This should show up as {channel}."
            await self.cog.send_message(message, self.text_channels[1], self.voice_channel, alert_target=True)

            updated_message = message.format(channel=self.voice_channel.mention)
            self.text_channels[1].send.assert_awaited_once_with(updated_message)

            mock_voice_channels.get.assert_called_once_with(self.voice_channel.id)
            self.bot.get_channel.assert_called_once_with(self.text_channels[1].id)
