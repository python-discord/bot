import asyncio
import unittest
from datetime import datetime, timezone
from unittest import mock
from unittest.mock import Mock

from discord import PermissionOverwrite

from bot.cogs.moderation import silence
from bot.constants import Channels, Guild, Roles
from tests.helpers import MockBot, MockContext, MockTextChannel, autospec


class SilenceNotifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.alert_channel = MockTextChannel()
        self.notifier = silence.SilenceNotifier(self.alert_channel)
        self.notifier.stop = self.notifier_stop_mock = Mock()
        self.notifier.start = self.notifier_start_mock = Mock()

    def test_add_channel_adds_channel(self):
        """Channel in FirstHash with current loop is added to internal set."""
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
        """Channel in FirstHash is removed from `_silenced_channels`."""
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
                self.alert_channel.send.assert_called_once_with(f"<@&{Roles.moderators}> currently silenced channels: ")
            self.alert_channel.send.reset_mock()

    async def test_notifier_skips_alert(self):
        """Alert is skipped on first loop or not an increment of 900."""
        test_cases = (0, 15, 5000)
        for current_loop in test_cases:
            with self.subTest(current_loop=current_loop):
                with mock.patch.object(self.notifier, "_current_loop", new=current_loop):
                    await self.notifier._notifier()
                    self.alert_channel.send.assert_not_called()


@autospec(silence.Silence, "muted_channel_perms", "muted_channel_times", pass_mocks=False)
class SilenceCogTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the general functionality of the Silence cog."""

    @autospec(silence, "Scheduler", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = silence.Silence(self.bot)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def test_init_cog_got_guild(self):
        """Bot got guild after it became available."""
        await self.cog._init_cog()
        self.bot.wait_until_guild_available.assert_awaited_once()
        self.bot.get_guild.assert_called_once_with(Guild.id)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def test_init_cog_got_role(self):
        """Got `Roles.verified` role from guild."""
        await self.cog._init_cog()
        guild = self.bot.get_guild()
        guild.get_role.assert_called_once_with(Roles.verified)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def test_init_cog_got_channels(self):
        """Got channels from bot."""
        await self.cog._init_cog()
        self.bot.get_channel.called_once_with(Channels.mod_alerts)
        self.bot.get_channel.called_once_with(Channels.mod_log)

    @autospec(silence, "SilenceNotifier")
    async def test_init_cog_got_notifier(self, notifier):
        """Notifier was started with channel."""
        mod_log = MockTextChannel()
        self.bot.get_channel.side_effect = (None, mod_log)
        await self.cog._init_cog()
        notifier.assert_called_once_with(self.cog._mod_log_channel)

    @autospec(silence, "SilenceNotifier", pass_mocks=False)
    async def test_init_cog_rescheduled(self):
        """`_reschedule_` coroutine was awaited."""
        self.cog._reschedule = mock.create_autospec(self.cog._reschedule, spec_set=True)
        await self.cog._init_cog()
        self.cog._reschedule.assert_awaited_once_with()

    def test_cog_unload_cancelled_tasks(self):
        """All scheduled tasks were cancelled."""
        self.cog.cog_unload()
        self.cog.scheduler.cancel_all.assert_called_once_with()

    @autospec(silence, "with_role_check")
    @mock.patch.object(silence, "MODERATION_ROLES", new=(1, 2, 3))
    def test_cog_check(self, role_check):
        """Role check was called with `MODERATION_ROLES`"""
        ctx = MockContext()
        self.cog.cog_check(ctx)
        role_check.assert_called_once_with(ctx, *(1, 2, 3))


@autospec(silence.Silence, "muted_channel_perms", "muted_channel_times", pass_mocks=False)
class RescheduleTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the rescheduling of cached unsilences."""

    @autospec(silence, "Scheduler", "SilenceNotifier", pass_mocks=False)
    def setUp(self):
        self.bot = MockBot()
        self.cog = silence.Silence(self.bot)
        self.cog._unsilence_wrapper = mock.create_autospec(self.cog._unsilence_wrapper, spec_set=True)

        with mock.patch.object(self.cog, "_reschedule", spec_set=True, autospec=True):
            asyncio.run(self.cog._init_cog())  # Populate instance attributes.

    async def test_skipped_missing_channel(self):
        """Did nothing because the channel couldn't be retrieved."""
        self.cog.muted_channel_times.items.return_value = [(123, -1), (123, 1), (123, 100000000000)]
        self.bot.get_channel.return_value = None

        await self.cog._reschedule()

        self.cog.notifier.add_channel.assert_not_called()
        self.cog._unsilence_wrapper.assert_not_called()
        self.cog.scheduler.schedule_later.assert_not_called()


@autospec(silence.Silence, "muted_channel_perms", "muted_channel_times", pass_mocks=False)
class SilenceTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the silence command and its related helper methods."""

    @autospec(silence.Silence, "_reschedule", pass_mocks=False)
    @autospec(silence, "Scheduler", "SilenceNotifier", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = silence.Silence(self.bot)
        self.cog._init_task = asyncio.Future()
        self.cog._init_task.set_result(None)

        asyncio.run(self.cog._init_cog())  # Populate instance attributes.

        self.channel = MockTextChannel()
        self.overwrite = PermissionOverwrite(stream=True, send_messages=True, add_reactions=False)
        self.channel.overwrites_for.return_value = self.overwrite

    async def test_sent_correct_message(self):
        """Appropriate failure/success message was sent by the command."""
        test_cases = (
            (0.0001, silence.MSG_SILENCE_SUCCESS.format(duration=0.0001), True,),
            (None, silence.MSG_SILENCE_PERMANENT, True,),
            (5, silence.MSG_SILENCE_FAIL, False,),
        )
        for duration, message, was_silenced in test_cases:
            ctx = MockContext()
            with self.subTest(was_silenced=was_silenced, message=message, duration=duration):
                with mock.patch.object(self.cog, "_silence", return_value=was_silenced):
                    await self.cog.silence.callback(self.cog, ctx, duration)
                    ctx.send.assert_called_once_with(message)

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

                self.assertFalse(await self.cog._silence(channel, True, None))
                channel.set_permissions.assert_not_called()

    async def test_silenced_channel(self):
        """Channel had `send_message` and `add_reactions` permissions revoked for verified role."""
        self.assertTrue(await self.cog._silence(self.channel, False, None))
        self.assertFalse(self.overwrite.send_messages)
        self.assertFalse(self.overwrite.add_reactions)
        self.channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_role,
            overwrite=self.overwrite
        )

    async def test_preserved_other_overwrites(self):
        """Channel's other unrelated overwrites were not changed."""
        prev_overwrite_dict = dict(self.overwrite)
        await self.cog._silence(self.channel, False, None)
        new_overwrite_dict = dict(self.overwrite)

        # Remove 'send_messages' & 'add_reactions' keys because they were changed by the method.
        del prev_overwrite_dict['send_messages']
        del prev_overwrite_dict['add_reactions']
        del new_overwrite_dict['send_messages']
        del new_overwrite_dict['add_reactions']

        self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)

    async def test_added_removed_notifier(self):
        """Channel was added to notifier if `persistent` was `True`, and removed if `False`."""
        with mock.patch.object(self.cog, "notifier", create=True):
            with self.subTest(persistent=True):
                await self.cog._silence(self.channel, True, None)
                self.cog.notifier.add_channel.assert_called_once()

        with mock.patch.object(self.cog, "notifier", create=True):
            with self.subTest(persistent=False):
                await self.cog._silence(self.channel, False, None)
                self.cog.notifier.add_channel.assert_not_called()

    async def test_cached_previous_overwrites(self):
        """Channel's previous overwrites were cached."""
        overwrite_json = '{"send_messages": true, "add_reactions": false}'
        await self.cog._silence(self.channel, False, None)
        self.cog.muted_channel_perms.set.assert_called_once_with(self.channel.id, overwrite_json)

    @autospec(silence, "datetime")
    async def test_cached_unsilence_time(self, datetime_mock):
        """The UTC POSIX timestamp for the unsilence was cached."""
        now_timestamp = 100
        duration = 15
        timestamp = now_timestamp + duration * 60
        datetime_mock.now.return_value = datetime.fromtimestamp(now_timestamp, tz=timezone.utc)

        ctx = MockContext(channel=self.channel)
        await self.cog.silence.callback(self.cog, ctx, duration)

        self.cog.muted_channel_times.set.assert_awaited_once_with(ctx.channel.id, timestamp)
        datetime_mock.now.assert_called_once_with(tz=timezone.utc)  # Ensure it's using an aware dt.

    async def test_cached_indefinite_time(self):
        """A value of -1 was cached for a permanent silence."""
        ctx = MockContext(channel=self.channel)
        await self.cog.silence.callback(self.cog, ctx, None)
        self.cog.muted_channel_times.set.assert_awaited_once_with(ctx.channel.id, -1)

    async def test_scheduled_task(self):
        """An unsilence task was scheduled."""
        ctx = MockContext(channel=self.channel)
        await self.cog.silence.callback(self.cog, ctx)
        self.cog.scheduler.schedule_later.assert_called_once()

    async def test_permanent_not_scheduled(self):
        """A task was not scheduled for a permanent silence."""
        ctx = MockContext(channel=self.channel)
        await self.cog.silence.callback(self.cog, ctx, None)
        self.cog.scheduler.schedule_later.assert_not_called()


@autospec(silence.Silence, "muted_channel_times", pass_mocks=False)
class UnsilenceTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the unsilence command and its related helper methods."""

    @autospec(silence.Silence, "_reschedule", pass_mocks=False)
    @autospec(silence, "Scheduler", "SilenceNotifier", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot(get_channel=lambda _: MockTextChannel())
        self.cog = silence.Silence(self.bot)
        self.cog._init_task = asyncio.Future()
        self.cog._init_task.set_result(None)

        perms_cache = mock.create_autospec(self.cog.muted_channel_perms, spec_set=True)
        self.cog.muted_channel_perms = perms_cache

        asyncio.run(self.cog._init_cog())  # Populate instance attributes.

        self.cog.scheduler.__contains__.return_value = True
        perms_cache.get.return_value = '{"send_messages": true, "add_reactions": false}'
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
        )
        for was_unsilenced, message, overwrite in test_cases:
            ctx = MockContext()
            with self.subTest(was_unsilenced=was_unsilenced, message=message, overwrite=overwrite):
                with mock.patch.object(self.cog, "_unsilence", return_value=was_unsilenced):
                    ctx.channel.overwrites_for.return_value = overwrite
                    await self.cog.unsilence.callback(self.cog, ctx)
                    ctx.channel.send.assert_called_once_with(message)

    async def test_skipped_already_unsilenced(self):
        """Permissions were not set and `False` was returned for an already unsilenced channel."""
        self.cog.scheduler.__contains__.return_value = False
        self.cog.muted_channel_perms.get.return_value = None
        channel = MockTextChannel()

        self.assertFalse(await self.cog._unsilence(channel))
        channel.set_permissions.assert_not_called()

    async def test_restored_overwrites(self):
        """Channel's `send_message` and `add_reactions` overwrites were restored."""
        await self.cog._unsilence(self.channel)
        self.channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_role,
            overwrite=self.overwrite,
        )

        # Recall that these values are determined by the fixture.
        self.assertTrue(self.overwrite.send_messages)
        self.assertFalse(self.overwrite.add_reactions)

    async def test_cache_miss_used_default_overwrites(self):
        """Both overwrites were set to None due previous values not being found in the cache."""
        self.cog.muted_channel_perms.get.return_value = None

        await self.cog._unsilence(self.channel)
        self.channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_role,
            overwrite=self.overwrite,
        )

        self.assertIsNone(self.overwrite.send_messages)
        self.assertIsNone(self.overwrite.add_reactions)

    async def test_cache_miss_sent_mod_alert(self):
        """A message was sent to the mod alerts channel."""
        self.cog.muted_channel_perms.get.return_value = None

        await self.cog._unsilence(self.channel)
        self.cog._mod_alerts_channel.send.assert_awaited_once()

    async def test_removed_notifier(self):
        """Channel was removed from `notifier`."""
        await self.cog._unsilence(self.channel)
        self.cog.notifier.remove_channel.assert_called_once_with(self.channel)

    async def test_deleted_cached_overwrite(self):
        """Channel was deleted from the overwrites cache."""
        await self.cog._unsilence(self.channel)
        self.cog.muted_channel_perms.delete.assert_awaited_once_with(self.channel.id)

    async def test_deleted_cached_time(self):
        """Channel was deleted from the timestamp cache."""
        await self.cog._unsilence(self.channel)
        self.cog.muted_channel_times.delete.assert_awaited_once_with(self.channel.id)

    async def test_cancelled_task(self):
        """The scheduled unsilence task should be cancelled."""
        await self.cog._unsilence(self.channel)
        self.cog.scheduler.cancel.assert_called_once_with(self.channel.id)

    async def test_preserved_other_overwrites(self):
        """Channel's other unrelated overwrites were not changed, including cache misses."""
        for overwrite_json in ('{"send_messages": true, "add_reactions": null}', None):
            with self.subTest(overwrite_json=overwrite_json):
                self.cog.muted_channel_perms.get.return_value = overwrite_json

                prev_overwrite_dict = dict(self.overwrite)
                await self.cog._unsilence(self.channel)
                new_overwrite_dict = dict(self.overwrite)

                # Remove these keys because they were modified by the unsilence.
                del prev_overwrite_dict['send_messages']
                del prev_overwrite_dict['add_reactions']
                del new_overwrite_dict['send_messages']
                del new_overwrite_dict['add_reactions']

                self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)
