import asyncio
import unittest
from datetime import datetime, timezone
from unittest import mock
from unittest.mock import Mock

from discord import PermissionOverwrite

from bot.cogs.moderation.silence import Silence, SilenceNotifier
from bot.constants import Channels, Emojis, Guild, Roles
from tests.helpers import MockBot, MockContext, MockTextChannel, autospec


class SilenceNotifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.alert_channel = MockTextChannel()
        self.notifier = SilenceNotifier(self.alert_channel)
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


@autospec(Silence, "muted_channel_perms", "muted_channel_times", pass_mocks=False)
class SilenceCogTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the general functionality of the Silence cog."""

    @autospec("bot.cogs.moderation.silence", "Scheduler", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Silence(self.bot)

    @autospec(Silence, "_reschedule", pass_mocks=False)
    @autospec("bot.cogs.moderation.silence", "SilenceNotifier", pass_mocks=False)
    async def test_init_cog_got_guild(self):
        """Bot got guild after it became available."""
        await self.cog._init_cog()
        self.bot.wait_until_guild_available.assert_awaited_once()
        self.bot.get_guild.assert_called_once_with(Guild.id)

    @autospec(Silence, "_reschedule", pass_mocks=False)
    @autospec("bot.cogs.moderation.silence", "SilenceNotifier", pass_mocks=False)
    async def test_init_cog_got_role(self):
        """Got `Roles.verified` role from guild."""
        await self.cog._init_cog()
        guild = self.bot.get_guild()
        guild.get_role.assert_called_once_with(Roles.verified)

    @autospec(Silence, "_reschedule", pass_mocks=False)
    @autospec("bot.cogs.moderation.silence", "SilenceNotifier", pass_mocks=False)
    async def test_init_cog_got_channels(self):
        """Got channels from bot."""
        await self.cog._init_cog()
        self.bot.get_channel.called_once_with(Channels.mod_alerts)
        self.bot.get_channel.called_once_with(Channels.mod_log)

    @autospec(Silence, "_reschedule", pass_mocks=False)
    @autospec("bot.cogs.moderation.silence", "SilenceNotifier")
    async def test_init_cog_got_notifier(self, notifier):
        """Notifier was started with channel."""
        mod_log = MockTextChannel()
        self.bot.get_channel.side_effect = (None, mod_log)
        await self.cog._init_cog()
        notifier.assert_called_once_with(self.cog._mod_log_channel)

    def test_cog_unload_cancelled_tasks(self):
        """All scheduled tasks were cancelled."""
        self.cog.cog_unload()
        self.cog.scheduler.cancel_all.assert_called_once_with()

    @autospec("bot.cogs.moderation.silence", "with_role_check")
    @mock.patch("bot.cogs.moderation.silence.MODERATION_ROLES", new=(1, 2, 3))
    def test_cog_check(self, role_check):
        """Role check was called with `MODERATION_ROLES`"""
        ctx = MockContext()
        self.cog.cog_check(ctx)
        role_check.assert_called_once_with(ctx, *(1, 2, 3))


@autospec(Silence, "muted_channel_perms", "muted_channel_times", pass_mocks=False)
class SilenceTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the silence command and its related helper methods."""

    @autospec(Silence, "_reschedule", pass_mocks=False)
    @autospec("bot.cogs.moderation.silence", "Scheduler", "SilenceNotifier", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Silence(self.bot)
        self.cog._init_task = asyncio.Future()
        self.cog._init_task.set_result(None)

        asyncio.run(self.cog._init_cog())  # Populate instance attributes.

        self.channel = MockTextChannel()
        self.overwrite = PermissionOverwrite(stream=True, send_messages=True, add_reactions=False)
        self.channel.overwrites_for.return_value = self.overwrite

    async def test_sent_correct_message(self):
        """Appropriate failure/success message was sent by the command."""
        test_cases = (
            (0.0001, f"{Emojis.check_mark} silenced current channel for 0.0001 minute(s).", True,),
            (None, f"{Emojis.check_mark} silenced current channel indefinitely.", True,),
            (5, f"{Emojis.cross_mark} current channel is already silenced.", False,),
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

    @autospec("bot.cogs.moderation.silence", "datetime")
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


@autospec(Silence, "muted_channel_times", pass_mocks=False)
class UnsilenceTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the unsilence command and its related helper methods."""

    @autospec(Silence, "_reschedule", pass_mocks=False)
    @autospec("bot.cogs.moderation.silence", "Scheduler", "SilenceNotifier", pass_mocks=False)
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Silence(self.bot)
        self.cog._init_task = asyncio.Future()
        self.cog._init_task.set_result(None)

        perms_cache = mock.create_autospec(self.cog.muted_channel_perms, spec_set=True)
        self.cog.muted_channel_perms = perms_cache

        asyncio.run(self.cog._init_cog())  # Populate instance attributes.

        perms_cache.get.return_value = '{"send_messages": true, "add_reactions": null}'
        self.channel = MockTextChannel()
        self.overwrite = PermissionOverwrite(stream=True, send_messages=False, add_reactions=False)
        self.channel.overwrites_for.return_value = self.overwrite

    async def test_sent_correct_message(self):
        """Appropriate failure/success message was sent by the command."""
        test_cases = (
            (True, f"{Emojis.check_mark} unsilenced current channel."),
            (False, f"{Emojis.cross_mark} current channel was not silenced.")
        )
        for was_unsilenced, message in test_cases:
            ctx = MockContext()
            with self.subTest(was_unsilenced=was_unsilenced, message=message):
                with mock.patch.object(self.cog, "_unsilence", return_value=was_unsilenced):
                    await self.cog.unsilence.callback(self.cog, ctx)
                    ctx.channel.send.assert_called_once_with(message)

    async def test_skipped_already_unsilenced(self):
        """Permissions were not set and `False` was returned for an already unsilenced channel."""
        self.cog.scheduler.__contains__.return_value = False
        self.cog.muted_channel_perms.get.return_value = None
        channel = MockTextChannel()

        self.assertFalse(await self.cog._unsilence(channel))
        channel.set_permissions.assert_not_called()

    async def test_unsilenced_channel(self):
        """Channel's `send_message` and `add_reactions` overwrites were restored."""
        await self.cog._unsilence(self.channel)
        self.channel.set_permissions.assert_awaited_once_with(
            self.cog._verified_role, overwrite=self.overwrite
        )

        # Recall that these values are determined by the fixture.
        self.assertTrue(self.overwrite.send_messages)
        self.assertIsNone(self.overwrite.add_reactions)

    async def test_removed_notifier(self):
        """Channel was removed from `notifier`."""
        await self.cog._unsilence(self.channel)
        self.cog.notifier.remove_channel.assert_called_once_with(self.channel)

    async def test_deleted_cached_overwrite(self):
        """Channel was deleted from the overwrites cache."""
        await self.cog._unsilence(self.channel)
        self.cog.muted_channel_perms.delete.assert_awaited_once_with(self.channel.id)

    async def test_preserved_other_overwrites(self):
        """Channel's other unrelated overwrites were not changed."""
        prev_overwrite_dict = dict(self.overwrite)
        await self.cog._unsilence(self.channel)
        new_overwrite_dict = dict(self.overwrite)

        # Remove 'send_messages' & 'add_reactions' keys because they were changed by the method.
        del prev_overwrite_dict['send_messages']
        del prev_overwrite_dict['add_reactions']
        del new_overwrite_dict['send_messages']
        del new_overwrite_dict['add_reactions']

        self.assertDictEqual(prev_overwrite_dict, new_overwrite_dict)
