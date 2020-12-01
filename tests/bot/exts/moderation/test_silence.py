import asyncio
import unittest
from datetime import datetime, timezone
from unittest import mock
from unittest.mock import AsyncMock, Mock

from async_rediscache import RedisSession
from discord import PermissionOverwrite

from bot.constants import Channels, Guild, Roles
from bot.exts.moderation import silence
from tests.helpers import MockBot, MockContext, MockGuild, MockMember, MockTextChannel, MockVoiceChannel, autospec

redis_session = None
redis_loop = asyncio.get_event_loop()


def setUpModule():  # noqa: N802
    """Create and connect to the fakeredis session."""
    global redis_session
    redis_session = RedisSession(use_fakeredis=True)
    redis_loop.run_until_complete(redis_session.connect())


def tearDownModule():  # noqa: N802
    """Close the fakeredis session."""
    if redis_session:
        redis_loop.run_until_complete(redis_session.close())


# Have to subclass it because builtins can't be patched.
class PatchedDatetime(datetime):
    """A datetime object with a mocked now() function."""

    now = mock.create_autospec(datetime, "now")


class SilenceNotifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.alert_channel = MockTextChannel()
        self.notifier = silence.SilenceNotifier(self.alert_channel)
        self.notifier.stop = self.notifier_stop_mock = Mock()
        self.notifier.start = self.notifier_start_mock = Mock()

    def test_add_channel_adds_channel(self):
        """Channel is added to `_silenced_channels` with the current loop."""
        channel = Mock()
        with mock.patch.object(self.notifier, "_silenced_channels") as silenced_channels:
            self.notifier.add_channel(channel)
        silenced_channels.__setitem__.assert_called_with(channel, self.notifier._current_loop)

    def test_add_channel_starts_loop(self):
        """Loop is started if `_silenced_channels` was empty."""
        self.notifier.add_channel(Mock())
        self.notifier_start_mock.assert_called_once()

    def test_add_channel_skips_start_with_channels(self):
        """Loop start is not called when `_silenced_channels` is not empty."""
        with mock.patch.object(self.notifier, "_silenced_channels"):
            self.notifier.add_channel(Mock())
        self.notifier_start_mock.assert_not_called()

    def test_remove_channel_removes_channel(self):
        """Channel is removed from `_silenced_channels`."""
        channel = Mock()
        with mock.patch.object(self.notifier, "_silenced_channels") as silenced_channels:
            self.notifier.remove_channel(channel)
        silenced_channels.__delitem__.assert_called_with(channel)

    def test_remove_channel_stops_loop(self):
        """Notifier loop is stopped if `_silenced_channels` is empty after remove."""
        with mock.patch.object(self.notifier, "_silenced_channels", __bool__=lambda _: False):
            self.notifier.remove_channel(Mock())
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
            with self.subTest(current_loop=current_loop):
                with mock.patch.object(self.notifier, "_current_loop", new=current_loop):
                    await self.notifier._notifier()
                    self.alert_channel.send.assert_not_called()


@autospec(silence.Silence, "previous_overwrites", "unsilence_timestamps", pass_mocks=False)
class SilenceCogTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the general functionality of the Silence cog."""

    @autospec(silence, "Scheduler", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = silence.Silence(self.bot)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def test_async_init_got_guild(self):
        """Bot got guild after it became available."""
        await self.cog._async_init()
        self.bot.wait_until_guild_available.assert_awaited_once()
        self.bot.get_guild.assert_called_once_with(Guild.id)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def test_async_init_got_role(self):
        """Got `Roles.verified` role from guild."""
        guild = self.bot.get_guild()
        guild.get_role.side_effect = lambda id_: Mock(id=id_)

        await self.cog._async_init()
        self.assertEqual(self.cog._verified_msg_role.id, Roles.verified)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def test_async_init_got_channels(self):
        """Got channels from bot."""
        self.bot.get_channel.side_effect = lambda id_: MockTextChannel(id=id_)

        await self.cog._async_init()
        self.assertEqual(self.cog._mod_alerts_channel.id, Channels.mod_alerts)

    @autospec(silence, "SilenceNotifier")
    async def test_async_init_got_notifier(self, notifier):
        """Notifier was started with channel."""
        self.bot.get_channel.side_effect = lambda id_: MockTextChannel(id=id_)

        await self.cog._async_init()
        notifier.assert_called_once_with(MockTextChannel(id=Channels.mod_log))
        self.assertEqual(self.cog.notifier, notifier.return_value)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def test_async_init_rescheduled(self):
        """`_reschedule_` coroutine was awaited."""
        self.cog._reschedule = mock.create_autospec(self.cog._reschedule)
        await self.cog._async_init()
        self.cog._reschedule.assert_awaited_once_with()

    def test_cog_unload_cancelled_tasks(self):
        """The init task was cancelled."""
        self.cog._init_task = asyncio.Future()
        self.cog.cog_unload()

        # It's too annoying to test cancel_all since it's a done callback and wrapped in a lambda.
        self.assertTrue(self.cog._init_task.cancelled())

    @autospec("discord.ext.commands", "has_any_role")
    @mock.patch.object(silence.constants, "MODERATION_ROLES", new=(1, 2, 3))
    async def test_cog_check(self, role_check):
        """Role check was called with `MODERATION_ROLES`"""
        ctx = MockContext()
        role_check.return_value.predicate = mock.AsyncMock()

        await self.cog.cog_check(ctx)
        role_check.assert_called_once_with(*(1, 2, 3))
        role_check.return_value.predicate.assert_awaited_once_with(ctx)

    @mock.patch.object(silence, "VOICE_CHANNELS")
    async def test_send_message(self, mock_voice_channels):
        """Test the send function reports to the correct channels."""
        text_channel_1 = MockTextChannel()
        text_channel_2 = MockTextChannel()

        voice_channel = MockVoiceChannel()
        voice_channel.name = "General/Offtopic"
        voice_channel.mention = f"#{voice_channel.name}"

        mock_voice_channels.get.return_value = text_channel_2.id

        def reset():
            text_channel_1.reset_mock()
            text_channel_2.reset_mock()
            voice_channel.reset_mock()
            mock_voice_channels.reset_mock()

        with self.subTest("Basic One Channel Test"):
            await self.cog.send_message("Text basic message.", text_channel_1, text_channel_2, False)
            text_channel_1.send.assert_called_once_with("Text basic message.")
            text_channel_2.send.assert_not_called()

        reset()
        with self.subTest("Basic Two Channel Test"):
            await self.cog.send_message("Text basic message.", text_channel_1, text_channel_2, True)
            text_channel_1.send.assert_called_once_with("Text basic message.")
            text_channel_2.send.assert_called_once_with("Text basic message.")

        reset()
        with self.subTest("Replacement One Channel Test"):
            message = "Current. The following should be replaced: current channel."
            await self.cog.send_message(message, text_channel_1, text_channel_2, False)

            text_channel_1.send.assert_called_once_with(message.replace("current channel", text_channel_1.mention))
            text_channel_2.send.assert_not_called()

        reset()
        with self.subTest("Replacement Two Channel Test"):
            message = "Current. The following should be replaced: current channel."
            await self.cog.send_message(message, text_channel_1, text_channel_2, True)

            text_channel_1.send.assert_called_once_with(message.replace("current channel", text_channel_1.mention))
            text_channel_2.send.assert_called_once_with(message)

        reset()
        with self.subTest("Text and Voice"):
            await self.cog.send_message("This should show up just here", text_channel_1, voice_channel, False)
            text_channel_1.send.assert_called_once_with("This should show up just here")

        with mock.patch.object(self.cog, "bot") as bot_mock:
            bot_mock.get_channel.return_value = text_channel_2

            reset()
            with self.subTest("Text and Voice"):
                message = "This should show up as current channel"
                await self.cog.send_message(message, text_channel_1, voice_channel, True)
                text_channel_1.send.assert_called_once_with(message.replace("current channel", voice_channel.mention))
                text_channel_2.send.assert_called_once_with(message.replace("current channel", voice_channel.mention))

                mock_voice_channels.get.assert_called_once_with(voice_channel.id)
                bot_mock.get_channel.assert_called_once_with(text_channel_2.id)
                bot_mock.reset_mock()

            reset()
            with self.subTest("Text and Voice Same Invocation"):
                message = "This should show up as current channel"
                await self.cog.send_message(message, text_channel_2, voice_channel, True)
                text_channel_2.send.assert_called_once_with(message.replace("current channel", voice_channel.mention))

                mock_voice_channels.get.assert_called_once_with(voice_channel.id)
                bot_mock.get_channel.assert_called_once_with(text_channel_2.id)
                bot_mock.reset_mock()

    async def test_force_voice_sync(self):
        """Tests the _force_voice_sync helper function."""
        await self.cog._async_init()

        members = []
        for _ in range(10):
            members.append(MockMember())

        afk_channel = MockVoiceChannel()
        channel = MockVoiceChannel(guild=MockGuild(afk_channel=afk_channel), members=members)

        await self.cog._force_voice_sync(channel)
        for member in members:
            self.assertEqual(member.move_to.call_count, 2)
            calls = [
                mock.call(afk_channel, reason="Muting VC member."),
                mock.call(channel, reason="Muting VC member.")
            ]
            member.move_to.assert_has_calls(calls, any_order=False)

    async def test_force_voice_sync_staff(self):
        """Tests to ensure _force_voice_sync does not kick staff members."""
        await self.cog._async_init()
        member = MockMember(roles=[self.cog._helper_role])

        await self.cog._force_voice_sync(MockVoiceChannel(members=[member]))
        member.move_to.assert_not_called()

    async def test_force_voice_sync_no_channel(self):
        """Test to ensure _force_voice_sync can create its own voice channel if one is not available."""
        await self.cog._async_init()

        channel = MockVoiceChannel(guild=MockGuild(afk_channel=None))
        new_channel = MockVoiceChannel(delete=AsyncMock())
        channel.guild.create_voice_channel.return_value = new_channel

        await self.cog._force_voice_sync(channel)

        # Check channel creation
        overwrites = {
            channel.guild.default_role: PermissionOverwrite(speak=False, connect=False, view_channel=False)
        }
        channel.guild.create_voice_channel.assert_called_once_with("mute-temp", overwrites=overwrites)

        # Check bot deleted channel
        new_channel.delete.assert_called_once_with(reason="Deleting temp mute channel.")

    async def test_voice_kick(self):
        """Test to ensure kick function can remove all members from a voice channel."""
        await self.cog._async_init()

        members = []
        for _ in range(10):
            members.append(MockMember())

        channel = MockVoiceChannel(members=members)
        await self.cog._kick_voice_members(channel)

        for member in members:
            member.move_to.assert_called_once_with(None, reason="Kicking member from voice channel.")

    async def test_voice_kick_staff(self):
        """Test to ensure voice kick skips staff members."""
        await self.cog._async_init()
        member = MockMember(roles=[self.cog._helper_role])

        await self.cog._kick_voice_members(MockVoiceChannel(members=[member]))
        member.move_to.assert_not_called()


@autospec(silence.Silence, "previous_overwrites", "unsilence_timestamps", pass_mocks=False)
class RescheduleTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the rescheduling of cached unsilences."""

    @autospec(silence, "Scheduler", "SilenceNotifier", pass_mocks=False)
    def setUp(self):
        self.bot = MockBot()
        self.cog = silence.Silence(self.bot)
        self.cog._unsilence_wrapper = mock.create_autospec(self.cog._unsilence_wrapper)

        with mock.patch.object(self.cog, "_reschedule", autospec=True):
            asyncio.run(self.cog._async_init())  # Populate instance attributes.

    async def test_skipped_missing_channel(self):
        """Did nothing because the channel couldn't be retrieved."""
        self.cog.unsilence_timestamps.items.return_value = [(123, -1), (123, 1), (123, 10000000000)]
        self.bot.get_channel.return_value = None

        await self.cog._reschedule()

        self.cog.notifier.add_channel.assert_not_called()
        self.cog._unsilence_wrapper.assert_not_called()
        self.cog.scheduler.schedule_later.assert_not_called()

    async def test_added_permanent_to_notifier(self):
        """Permanently silenced channels were added to the notifier."""
        channels = [MockTextChannel(id=123), MockTextChannel(id=456)]
        self.bot.get_channel.side_effect = channels
        self.cog.unsilence_timestamps.items.return_value = [(123, -1), (456, -1)]

        await self.cog._reschedule()

        self.cog.notifier.add_channel.assert_any_call(channels[0])
        self.cog.notifier.add_channel.assert_any_call(channels[1])

        self.cog._unsilence_wrapper.assert_not_called()
        self.cog.scheduler.schedule_later.assert_not_called()

    async def test_unsilenced_expired(self):
        """Unsilenced expired silences."""
        channels = [MockTextChannel(id=123), MockTextChannel(id=456)]
        self.bot.get_channel.side_effect = channels
        self.cog.unsilence_timestamps.items.return_value = [(123, 100), (456, 200)]

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
        self.cog.unsilence_timestamps.items.return_value = [(123, 2000), (456, 3000)]
        silence.datetime.now.return_value = datetime.fromtimestamp(1000, tz=timezone.utc)

        self.cog._unsilence_wrapper = mock.MagicMock()
        unsilence_return = self.cog._unsilence_wrapper.return_value

        await self.cog._reschedule()

        # Yuck.
        calls = [mock.call(1000, 123, unsilence_return), mock.call(2000, 456, unsilence_return)]
        self.cog.scheduler.schedule_later.assert_has_calls(calls)

        unsilence_calls = [mock.call(channel) for channel in channels]
        self.cog._unsilence_wrapper.assert_has_calls(unsilence_calls)

        self.cog.notifier.add_channel.assert_not_called()


@autospec(silence.Silence, "previous_overwrites", "unsilence_timestamps", pass_mocks=False)
class SilenceTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the silence command and its related helper methods."""

    @autospec(silence.Silence, "_reschedule", pass_mocks=False)
    @autospec(silence, "Scheduler", "SilenceNotifier", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = silence.Silence(self.bot)
        self.cog._init_task = asyncio.Future()
        self.cog._init_task.set_result(None)

        # Avoid unawaited coroutine warnings.
        self.cog.scheduler.schedule_later.side_effect = lambda delay, task_id, coro: coro.close()

        asyncio.run(self.cog._async_init())  # Populate instance attributes.

        self.text_channel = MockTextChannel()
        self.text_overwrite = PermissionOverwrite(stream=True, send_messages=True, add_reactions=False)
        self.text_channel.overwrites_for.return_value = self.text_overwrite

        self.voice_channel = MockVoiceChannel()
        self.voice_overwrite = PermissionOverwrite(speak=True)
        self.voice_channel.overwrites_for.return_value = self.voice_overwrite

    async def test_sent_correct_message(self):
        """Appropriate failure/success message was sent by the command."""
        test_cases = (
            (0.0001, silence.MSG_SILENCE_SUCCESS.format(duration=0.0001), True,),
            (None, silence.MSG_SILENCE_PERMANENT, True,),
            (5, silence.MSG_SILENCE_FAIL, False,),
        )
        for duration, message, was_silenced in test_cases:
            ctx = MockContext()
            with mock.patch.object(self.cog, "_set_silence_overwrites", return_value=was_silenced):
                with self.subTest(was_silenced=was_silenced, message=message, duration=duration):
                    await self.cog.silence.callback(self.cog, ctx, duration)
                    ctx.channel.send.assert_called_once_with(message)

    @mock.patch.object(silence.Silence, "_set_silence_overwrites", return_value=True)
    @mock.patch.object(silence.Silence, "_force_voice_sync")
    async def test_sent_to_correct_channel(self, voice_sync, _):
        """Test function sends messages to the correct channels."""
        text_channel = MockTextChannel()
        voice_channel = MockVoiceChannel()
        ctx = MockContext()

        test_cases = (
            (None, silence.MSG_SILENCE_SUCCESS.format(duration=10)),
            (text_channel, silence.MSG_SILENCE_SUCCESS.format(duration=10)),
            (voice_channel, silence.MSG_SILENCE_SUCCESS.format(duration=10)),
            (ctx.channel, silence.MSG_SILENCE_SUCCESS.format(duration=10)),
        )

        for target, message in test_cases:
            with self.subTest(target_channel=target, message=message):
                with mock.patch.object(self.cog, "bot") as bot_mock:
                    bot_mock.get_channel.return_value = AsyncMock()
                    await self.cog.silence.callback(self.cog, ctx, 10, False, channel=target)

                if ctx.channel == target or target is None:
                    ctx.channel.send.assert_called_once_with(message)

                else:
                    ctx.channel.send.assert_called_once_with(message.replace("current channel", target.mention))
                    if isinstance(target, MockTextChannel):
                        target.send.assert_called_once_with(message)
                    else:
                        voice_sync.assert_called_once_with(target)

            ctx.channel.send.reset_mock()
            if target is not None and isinstance(target, MockTextChannel):
                target.send.reset_mock()

    @mock.patch.object(silence.Silence, "_set_silence_overwrites", return_value=True)
    @mock.patch.object(silence.Silence, "_kick_voice_members")
    @mock.patch.object(silence.Silence, "_force_voice_sync")
    async def test_sync_or_kick_called(self, sync, kick, _):
        """Tests if silence command calls kick or sync on voice channels when appropriate."""
        channel = MockVoiceChannel()
        ctx = MockContext()

        with mock.patch.object(self.cog, "bot") as bot_mock:
            bot_mock.get_channel.return_value = AsyncMock()

            with self.subTest("Test calls kick"):
                await self.cog.silence.callback(self.cog, ctx, 10, kick=True, channel=channel)
                kick.assert_called_once_with(channel)
                sync.assert_not_called()

            kick.reset_mock()
            sync.reset_mock()

            with self.subTest("Test calls sync"):
                await self.cog.silence.callback(self.cog, ctx, 10, kick=False, channel=channel)
                sync.assert_called_once_with(channel)
                kick.assert_not_called()

    async def test_skipped_already_silenced(self):
        """Permissions were not set and `False` was returned for an already silenced channel."""
        subtests = (
            (False, PermissionOverwrite(send_messages=False, add_reactions=False)),
            (True, PermissionOverwrite(send_messages=True, add_reactions=True)),
            (True, PermissionOverwrite(send_messages=False, add_reactions=False)),
        )

        for contains, overwrite in subtests:
            with self.subTest(contains=contains, overwrite=overwrite):
                self.cog.scheduler.__contains__.return_value = contains
                channel = MockTextChannel()
                channel.overwrites_for.return_value = overwrite

                self.assertFalse(await self.cog._set_silence_overwrites(channel))
                channel.set_permissions.assert_not_called()

    async def test_silenced_channel(self):
        """Channel had `send_message` and `add_reactions` permissions revoked for verified role."""
        self.assertTrue(await self.cog._set_silence_overwrites(self.text_channel))
        self.assertFalse(self.text_overwrite.send_messages)
        self.assertFalse(self.text_overwrite.add_reactions)
        self.text_channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_msg_role,
            overwrite=self.text_overwrite
        )

    async def test_preserved_other_overwrites(self):
        """Channel's other unrelated overwrites were not changed."""
        prev_overwrite_dict = dict(self.text_overwrite)
        await self.cog._set_silence_overwrites(self.text_channel)
        new_overwrite_dict = dict(self.text_overwrite)

        # Remove 'send_messages' & 'add_reactions' keys because they were changed by the method.
        del prev_overwrite_dict['send_messages']
        del prev_overwrite_dict['add_reactions']
        del new_overwrite_dict['send_messages']
        del new_overwrite_dict['add_reactions']

        self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)

    async def test_temp_not_added_to_notifier(self):
        """Channel was not added to notifier if a duration was set for the silence."""
        with mock.patch.object(self.cog, "_set_silence_overwrites", return_value=True):
            await self.cog.silence.callback(self.cog, MockContext(), 15)
            self.cog.notifier.add_channel.assert_not_called()

    async def test_indefinite_added_to_notifier(self):
        """Channel was added to notifier if a duration was not set for the silence."""
        with mock.patch.object(self.cog, "_set_silence_overwrites", return_value=True):
            await self.cog.silence.callback(self.cog, MockContext(), None)
            self.cog.notifier.add_channel.assert_called_once()

    async def test_silenced_not_added_to_notifier(self):
        """Channel was not added to the notifier if it was already silenced."""
        with mock.patch.object(self.cog, "_set_silence_overwrites", return_value=False):
            await self.cog.silence.callback(self.cog, MockContext(), 15)
            self.cog.notifier.add_channel.assert_not_called()

    async def test_cached_previous_overwrites(self):
        """Channel's previous overwrites were cached."""
        overwrite_json = '{"send_messages": true, "add_reactions": false}'
        await self.cog._set_silence_overwrites(self.text_channel)
        self.cog.previous_overwrites.set.assert_called_once_with(self.text_channel.id, overwrite_json)

    @autospec(silence, "datetime")
    async def test_cached_unsilence_time(self, datetime_mock):
        """The UTC POSIX timestamp for the unsilence was cached."""
        now_timestamp = 100
        duration = 15
        timestamp = now_timestamp + duration * 60
        datetime_mock.now.return_value = datetime.fromtimestamp(now_timestamp, tz=timezone.utc)

        ctx = MockContext(channel=self.text_channel)
        await self.cog.silence.callback(self.cog, ctx, duration)

        self.cog.unsilence_timestamps.set.assert_awaited_once_with(ctx.channel.id, timestamp)
        datetime_mock.now.assert_called_once_with(tz=timezone.utc)  # Ensure it's using an aware dt.

    async def test_cached_indefinite_time(self):
        """A value of -1 was cached for a permanent silence."""
        ctx = MockContext(channel=self.text_channel)
        await self.cog.silence.callback(self.cog, ctx, None)
        self.cog.unsilence_timestamps.set.assert_awaited_once_with(ctx.channel.id, -1)

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
        await self.cog.silence.callback(self.cog, ctx, None)
        self.cog.scheduler.schedule_later.assert_not_called()

    async def test_correct_permission_updates(self):
        """Tests if _set_silence_overwrites can correctly get and update permissions."""
        self.assertTrue(await self.cog._set_silence_overwrites(self.text_channel))
        self.assertFalse(self.text_overwrite.send_messages or self.text_overwrite.add_reactions)

        self.assertTrue(await self.cog._set_silence_overwrites(self.voice_channel))
        self.assertFalse(self.voice_overwrite.speak)

        self.assertTrue(await self.cog._set_silence_overwrites(self.voice_channel, True))
        self.assertFalse(self.voice_overwrite.speak or self.voice_overwrite.connect)


@autospec(silence.Silence, "unsilence_timestamps", pass_mocks=False)
class UnsilenceTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the unsilence command and its related helper methods."""

    @autospec(silence.Silence, "_reschedule", pass_mocks=False)
    @autospec(silence, "Scheduler", "SilenceNotifier", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot(get_channel=lambda _: MockTextChannel())
        self.cog = silence.Silence(self.bot)
        self.cog._init_task = asyncio.Future()
        self.cog._init_task.set_result(None)

        overwrites_cache = mock.create_autospec(self.cog.previous_overwrites, spec_set=True)
        self.cog.previous_overwrites = overwrites_cache

        asyncio.run(self.cog._async_init())  # Populate instance attributes.

        self.cog.scheduler.__contains__.return_value = True
        overwrites_cache.get.return_value = '{"send_messages": true, "add_reactions": false}'
        self.channel = MockTextChannel()
        self.overwrite = PermissionOverwrite(stream=True, send_messages=False, add_reactions=False)
        self.channel.overwrites_for.return_value = self.overwrite

    async def test_sent_correct_message(self):
        """Appropriate failure/success message was sent by the command."""
        unsilenced_overwrite = PermissionOverwrite(send_messages=True, add_reactions=True)
        test_cases = (
            (True, silence.MSG_UNSILENCE_SUCCESS, unsilenced_overwrite),
            (False, silence.MSG_UNSILENCE_FAIL, unsilenced_overwrite),
            (False, silence.MSG_UNSILENCE_MANUAL, self.overwrite),
            (False, silence.MSG_UNSILENCE_MANUAL, PermissionOverwrite(send_messages=False)),
            (False, silence.MSG_UNSILENCE_MANUAL, PermissionOverwrite(add_reactions=False)),
        )
        for was_unsilenced, message, overwrite in test_cases:
            ctx = MockContext()
            with self.subTest(was_unsilenced=was_unsilenced, message=message, overwrite=overwrite):
                with mock.patch.object(self.cog, "_unsilence", return_value=was_unsilenced):
                    ctx.channel.overwrites_for.return_value = overwrite
                    await self.cog.unsilence.callback(self.cog, ctx)
                    ctx.channel.send.assert_called_once_with(message)

    async def test_sent_to_correct_channel(self):
        """Test function sends messages to the correct channels."""
        unsilenced_overwrite = PermissionOverwrite(send_messages=True, add_reactions=True)
        text_channel = MockTextChannel()
        ctx = MockContext()

        test_cases = (
            (None, silence.MSG_UNSILENCE_SUCCESS.format(duration=10)),
            (text_channel, silence.MSG_UNSILENCE_SUCCESS.format(duration=10)),
            (ctx.channel, silence.MSG_UNSILENCE_SUCCESS.format(duration=10)),
        )

        for target, message in test_cases:
            with self.subTest(target_channel=target, message=message):
                with mock.patch.object(self.cog, "_unsilence", return_value=True):
                    # Assign Return
                    if ctx.channel == target or target is None:
                        ctx.channel.overwrites_for.return_value = unsilenced_overwrite
                    else:
                        target.overwrites_for.return_value = unsilenced_overwrite

                    await self.cog.unsilence.callback(self.cog, ctx, channel=target)

                    # Check Messages
                    if ctx.channel == target or target is None:
                        ctx.channel.send.assert_called_once_with(message)
                    else:
                        ctx.channel.send.assert_called_once_with(
                            message.replace("current channel", text_channel.mention)
                        )
                        target.send.assert_called_once_with(message)

            ctx.channel.send.reset_mock()
            if target is not None:
                target.send.reset_mock()

    async def test_skipped_already_unsilenced(self):
        """Permissions were not set and `False` was returned for an already unsilenced channel."""
        self.cog.scheduler.__contains__.return_value = False
        self.cog.previous_overwrites.get.return_value = None
        channel = MockTextChannel()

        self.assertFalse(await self.cog._unsilence(channel))
        channel.set_permissions.assert_not_called()

    async def test_restored_overwrites(self):
        """Channel's `send_message` and `add_reactions` overwrites were restored."""
        await self.cog._unsilence(self.channel)
        self.channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_msg_role,
            overwrite=self.overwrite,
        )

        # Recall that these values are determined by the fixture.
        self.assertTrue(self.overwrite.send_messages)
        self.assertFalse(self.overwrite.add_reactions)

    async def test_cache_miss_used_default_overwrites(self):
        """Both overwrites were set to None due previous values not being found in the cache."""
        self.cog.previous_overwrites.get.return_value = None

        await self.cog._unsilence(self.channel)
        self.channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_msg_role,
            overwrite=self.overwrite,
        )

        self.assertIsNone(self.overwrite.send_messages)
        self.assertIsNone(self.overwrite.add_reactions)

    async def test_cache_miss_sent_mod_alert(self):
        """A message was sent to the mod alerts channel."""
        self.cog.previous_overwrites.get.return_value = None

        await self.cog._unsilence(self.channel)
        self.cog._mod_alerts_channel.send.assert_awaited_once()
        self.cog._mod_alerts_channel.send.reset_mock()

        await self.cog._unsilence(MockVoiceChannel())
        self.cog._mod_alerts_channel.send.assert_awaited_once()

    async def test_removed_notifier(self):
        """Channel was removed from `notifier`."""
        await self.cog._unsilence(self.channel)
        self.cog.notifier.remove_channel.assert_called_once_with(self.channel)

    async def test_deleted_cached_overwrite(self):
        """Channel was deleted from the overwrites cache."""
        await self.cog._unsilence(self.channel)
        self.cog.previous_overwrites.delete.assert_awaited_once_with(self.channel.id)

    async def test_deleted_cached_time(self):
        """Channel was deleted from the timestamp cache."""
        await self.cog._unsilence(self.channel)
        self.cog.unsilence_timestamps.delete.assert_awaited_once_with(self.channel.id)

    async def test_cancelled_task(self):
        """The scheduled unsilence task should be cancelled."""
        await self.cog._unsilence(self.channel)
        self.cog.scheduler.cancel.assert_called_once_with(self.channel.id)

    async def test_preserved_other_overwrites(self):
        """Channel's other unrelated overwrites were not changed, including cache misses."""
        for overwrite_json in ('{"send_messages": true, "add_reactions": null}', None):
            with self.subTest(overwrite_json=overwrite_json):
                self.cog.previous_overwrites.get.return_value = overwrite_json

                prev_overwrite_dict = dict(self.overwrite)
                await self.cog._unsilence(self.channel)
                new_overwrite_dict = dict(self.overwrite)

                # Remove these keys because they were modified by the unsilence.
                del prev_overwrite_dict['send_messages']
                del prev_overwrite_dict['add_reactions']
                del new_overwrite_dict['send_messages']
                del new_overwrite_dict['add_reactions']

                self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)

    @mock.patch.object(silence.Silence, "_unsilence", return_value=False)
    @mock.patch.object(silence.Silence, "send_message")
    async def test_unsilence_helper_fail(self, send_message, _):
        """Tests unsilence_wrapper when `_unsilence` fails."""
        ctx = MockContext()

        text_channel = MockTextChannel()
        text_role = self.cog.bot.get_guild(Guild.id).get_role(Roles.verified)

        voice_channel = MockVoiceChannel()
        voice_role = self.cog.bot.get_guild(Guild.id).get_role(Roles.voice_verified)

        test_cases = (
            (ctx, text_channel, text_role, True, silence.MSG_UNSILENCE_FAIL),
            (ctx, text_channel, text_role, False, silence.MSG_UNSILENCE_MANUAL),
            (ctx, voice_channel, voice_role, True, silence.MSG_UNSILENCE_FAIL),
            (ctx, voice_channel, voice_role, False, silence.MSG_UNSILENCE_MANUAL),
        )

        class PermClass:
            """Class to Mock return permissions"""
            def __init__(self, value: bool):
                self.val = value

            def __getattr__(self, item):
                return self.val

        for context, channel, role, permission, message in test_cases:
            with mock.patch.object(channel, "overwrites_for", return_value=PermClass(permission)) as overwrites:
                with self.subTest(channel=channel, message=message):
                    await self.cog._unsilence_wrapper(channel, context)

                    overwrites.assert_called_once_with(role)
                    send_message.assert_called_once_with(message, ctx.channel, channel)

                    send_message.reset_mock()

    @mock.patch.object(silence.Silence, "_force_voice_sync")
    @mock.patch.object(silence.Silence, "send_message")
    async def test_correct_overwrites(self, send_message, _):
        """Tests the overwrites returned by the _unsilence_wrapper are correct for voice and text channels."""
        ctx = MockContext()

        text_channel = MockTextChannel()
        text_role = self.cog.bot.get_guild(Guild.id).get_role(Roles.verified)

        voice_channel = MockVoiceChannel()
        voice_role = self.cog.bot.get_guild(Guild.id).get_role(Roles.voice_verified)

        async def reset():
            await text_channel.set_permissions(text_role, PermissionOverwrite(send_messages=False, add_reactions=False))
            await voice_channel.set_permissions(voice_role, PermissionOverwrite(speak=False, connect=False))

            text_channel.reset_mock()
            voice_channel.reset_mock()
            send_message.reset_mock()
        await reset()

        default_text_overwrites = text_channel.overwrites_for(text_role)
        default_voice_overwrites = voice_channel.overwrites_for(voice_role)

        test_cases = (
            (ctx, text_channel, text_role, default_text_overwrites, silence.MSG_UNSILENCE_SUCCESS),
            (ctx, voice_channel, voice_role, default_voice_overwrites, silence.MSG_UNSILENCE_SUCCESS),
            (ctx, ctx.channel, text_role, ctx.channel.overwrites_for(text_role), silence.MSG_UNSILENCE_SUCCESS),
            (None, text_channel, text_role, default_text_overwrites, silence.MSG_UNSILENCE_SUCCESS),
        )

        for context, channel, role, overwrites, message in test_cases:
            with self.subTest(ctx=context, channel=channel):
                await self.cog._unsilence_wrapper(channel, context)

                if context is None:
                    send_message.assert_called_once_with(message, channel, channel, True)
                else:
                    send_message.assert_called_once_with(message, context.channel, channel, True)

                channel.set_permissions.assert_called_once_with(role, overwrite=overwrites)
                if channel != ctx.channel:
                    ctx.channel.send.assert_not_called()

            await reset()
