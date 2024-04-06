import inspect
import textwrap
import unittest
from unittest.mock import ANY, AsyncMock, DEFAULT, MagicMock, Mock, patch

from discord.errors import NotFound

from bot.constants import Event
from bot.exts.moderation.clean import Clean
from bot.exts.moderation.infraction import _utils
from bot.exts.moderation.infraction.infractions import Infractions
from bot.exts.moderation.infraction.management import ModManagement
from tests.helpers import MockBot, MockContext, MockGuild, MockMember, MockRole, MockUser, autospec


class TruncationTests(unittest.IsolatedAsyncioTestCase):
    """Tests for ban and kick command reason truncation."""

    def setUp(self):
        self.me = MockMember(id=7890, roles=[MockRole(id=7890, position=5)])
        self.bot = MockBot()
        self.cog = Infractions(self.bot)
        self.user = MockMember(id=1234, roles=[MockRole(id=3577, position=10)])
        self.target = MockMember(id=1265, roles=[MockRole(id=9876, position=1)])
        self.guild = MockGuild(id=4567)
        self.ctx = MockContext(me=self.me, bot=self.bot, author=self.user, guild=self.guild)

    @patch("bot.exts.moderation.infraction._utils.get_active_infraction")
    @patch("bot.exts.moderation.infraction._utils.post_infraction")
    async def test_apply_ban_reason_truncation(self, post_infraction_mock, get_active_mock):
        """Should truncate reason for `ctx.guild.ban`."""
        get_active_mock.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        self.cog.apply_infraction = AsyncMock()
        self.bot.get_cog.return_value = AsyncMock()
        self.cog.mod_log.ignore = Mock()
        self.ctx.guild.ban = AsyncMock()

        infraction_reason = "foo bar" * 3000

        await self.cog.apply_ban(self.ctx, self.target, infraction_reason)
        self.cog.apply_infraction.assert_awaited_once_with(
            self.ctx, {"foo": "bar", "purge": ""}, self.target, ANY
        )

        action = self.cog.apply_infraction.call_args.args[-1]
        await action()
        self.ctx.guild.ban.assert_awaited_once_with(
            self.target,
            reason=textwrap.shorten(infraction_reason, 512, placeholder="..."),
            delete_message_days=0
        )

        # Assert that the reason sent to the database isn't truncated.
        post_infraction_mock.assert_awaited_once()
        self.assertEqual(post_infraction_mock.call_args.args[3], infraction_reason)

    @patch("bot.exts.moderation.infraction._utils.post_infraction")
    async def test_apply_kick_reason_truncation(self, post_infraction_mock):
        """Should truncate reason for `Member.kick`."""
        post_infraction_mock.return_value = {"foo": "bar"}

        self.cog.apply_infraction = AsyncMock()
        self.cog.mod_log.ignore = Mock()
        self.target.kick = AsyncMock()

        infraction_reason = "foo bar" * 3000

        await self.cog.apply_kick(self.ctx, self.target, infraction_reason)
        self.cog.apply_infraction.assert_awaited_once_with(
            self.ctx, {"foo": "bar"}, self.target, ANY
        )

        action = self.cog.apply_infraction.call_args.args[-1]
        await action()
        self.target.kick.assert_awaited_once_with(reason=textwrap.shorten(infraction_reason, 512, placeholder="..."))

        # Assert that the reason sent to the database isn't truncated.
        post_infraction_mock.assert_awaited_once()
        self.assertEqual(post_infraction_mock.call_args.args[3], infraction_reason)


@patch("bot.exts.moderation.infraction.infractions.constants.Roles.voice_verified", new=123456)
class VoiceMuteTests(unittest.IsolatedAsyncioTestCase):
    """Tests for voice mute related functions and commands."""

    def setUp(self):
        self.bot = MockBot()
        self.mod = MockMember(roles=[MockRole(id=7890123, position=10)])
        self.user = MockMember(roles=[MockRole(id=123456, position=1)])
        self.guild = MockGuild()
        self.ctx = MockContext(bot=self.bot, author=self.mod)
        self.cog = Infractions(self.bot)

    async def test_permanent_voice_mute(self):
        """Should call voice mute applying function without expiry."""
        self.cog.apply_voice_mute = AsyncMock()
        self.assertIsNone(await self.cog.voicemute(self.cog, self.ctx, self.user, reason="foobar"))
        self.cog.apply_voice_mute.assert_awaited_once_with(self.ctx, self.user, "foobar", duration_or_expiry=None)

    async def test_temporary_voice_mute(self):
        """Should call voice mute applying function with expiry."""
        self.cog.apply_voice_mute = AsyncMock()
        self.assertIsNone(await self.cog.tempvoicemute(self.cog, self.ctx, self.user, "baz", reason="foobar"))
        self.cog.apply_voice_mute.assert_awaited_once_with(self.ctx, self.user, "foobar", duration_or_expiry="baz")

    async def test_voice_unmute(self):
        """Should call infraction pardoning function."""
        self.cog.pardon_infraction = AsyncMock()
        self.assertIsNone(await self.cog.unvoicemute(self.cog, self.ctx, self.user, pardon_reason="foobar"))
        self.cog.pardon_infraction.assert_awaited_once_with(self.ctx, "voice_mute", self.user, "foobar")

    async def test_voice_unmute_reasonless(self):
        """Should call infraction pardoning function without a pardon reason."""
        self.cog.pardon_infraction = AsyncMock()
        self.assertIsNone(await self.cog.unvoicemute(self.cog, self.ctx, self.user))
        self.cog.pardon_infraction.assert_awaited_once_with(self.ctx, "voice_mute", self.user, None)

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_mute_user_have_active_infraction(self, get_active_infraction, post_infraction_mock):
        """Should return early when user already have Voice Mute infraction."""
        get_active_infraction.return_value = {"foo": "bar"}
        self.assertIsNone(await self.cog.apply_voice_mute(self.ctx, self.user, "foobar"))
        get_active_infraction.assert_awaited_once_with(self.ctx, self.user, "voice_mute")
        post_infraction_mock.assert_not_awaited()

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_mute_infraction_post_failed(self, get_active_infraction, post_infraction_mock):
        """Should return early when posting infraction fails."""
        self.cog.mod_log.ignore = MagicMock()
        get_active_infraction.return_value = None
        post_infraction_mock.return_value = None
        self.assertIsNone(await self.cog.apply_voice_mute(self.ctx, self.user, "foobar"))
        post_infraction_mock.assert_awaited_once()
        self.cog.mod_log.ignore.assert_not_called()

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_mute_infraction_post_add_kwargs(self, get_active_infraction, post_infraction_mock):
        """Should pass all kwargs passed to apply_voice_mute to post_infraction."""
        get_active_infraction.return_value = None
        # We don't want that this continue yet
        post_infraction_mock.return_value = None
        self.assertIsNone(await self.cog.apply_voice_mute(self.ctx, self.user, "foobar", my_kwarg=23))
        post_infraction_mock.assert_awaited_once_with(
            self.ctx, self.user, "voice_mute", "foobar", active=True, my_kwarg=23
        )

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_mute_mod_log_ignore(self, get_active_infraction, post_infraction_mock):
        """Should ignore Voice Verified role removing."""
        self.cog.mod_log.ignore = MagicMock()
        self.cog.apply_infraction = AsyncMock()
        self.user.remove_roles = MagicMock(return_value="my_return_value")

        get_active_infraction.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        self.assertIsNone(await self.cog.apply_voice_mute(self.ctx, self.user, "foobar"))
        self.cog.mod_log.ignore.assert_called_once_with(Event.member_update, self.user.id)

    async def action_tester(self, action, reason: str) -> None:
        """Helper method to test voice mute action."""
        self.assertTrue(inspect.iscoroutinefunction(action))
        await action()

        self.user.move_to.assert_called_once_with(None, reason=ANY)
        self.user.remove_roles.assert_called_once_with(self.cog._voice_verified_role, reason=reason)

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_mute_apply_infraction(self, get_active_infraction, post_infraction_mock):
        """Should ignore Voice Verified role removing."""
        self.cog.mod_log.ignore = MagicMock()
        self.cog.apply_infraction = AsyncMock()

        get_active_infraction.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        reason = "foobar"
        self.assertIsNone(await self.cog.apply_voice_mute(self.ctx, self.user, reason))
        self.cog.apply_infraction.assert_awaited_once_with(self.ctx, {"foo": "bar"}, self.user, ANY)

        await self.action_tester(self.cog.apply_infraction.call_args[0][-1], reason)

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_mute_truncate_reason(self, get_active_infraction, post_infraction_mock):
        """Should truncate reason for voice mute."""
        self.cog.mod_log.ignore = MagicMock()
        self.cog.apply_infraction = AsyncMock()

        get_active_infraction.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        self.assertIsNone(await self.cog.apply_voice_mute(self.ctx, self.user, "foobar" * 3000))
        self.cog.apply_infraction.assert_awaited_once_with(self.ctx, {"foo": "bar"}, self.user, ANY)

        # Test action
        action = self.cog.apply_infraction.call_args[0][-1]
        await self.action_tester(action, textwrap.shorten("foobar" * 3000, 512, placeholder="..."))

    @autospec(_utils, "post_infraction", "get_active_infraction", return_value=None)
    @autospec(Infractions, "apply_infraction")
    async def test_voice_mute_user_left_guild(self, apply_infraction_mock, post_infraction_mock, _):
        """Should voice mute user that left the guild without throwing an error."""
        infraction = {"foo": "bar"}
        post_infraction_mock.return_value = {"foo": "bar"}

        user = MockUser()
        await self.cog.voicemute(self.cog, self.ctx, user, reason=None)
        post_infraction_mock.assert_called_once_with(self.ctx, user, "voice_mute", None, active=True,
                                                     duration_or_expiry=None)
        apply_infraction_mock.assert_called_once_with(self.cog, self.ctx, infraction, user, ANY)

        # Test action
        action = self.cog.apply_infraction.call_args[0][-1]
        self.assertTrue(inspect.iscoroutinefunction(action))
        await action()

    async def test_voice_unmute_user_not_found(self):
        """Should include info to return dict when user was not found from guild."""
        self.guild.get_member.return_value = None
        self.guild.fetch_member.side_effect = NotFound(Mock(status=404), "Not found")
        result = await self.cog.pardon_voice_mute(self.user.id, self.guild)
        self.assertEqual(result, {"Info": "User was not found in the guild."})

    @patch("bot.exts.moderation.infraction.infractions._utils.notify_pardon")
    @patch("bot.exts.moderation.infraction.infractions.format_user")
    async def test_voice_unmute_user_found(self, format_user_mock, notify_pardon_mock):
        """Should add role back with ignoring, notify user and return log dictionary.."""
        self.guild.get_member.return_value = self.user
        notify_pardon_mock.return_value = True
        format_user_mock.return_value = "my-user"

        result = await self.cog.pardon_voice_mute(self.user.id, self.guild)
        self.assertEqual(result, {
            "Member": "my-user",
            "DM": "Sent"
        })
        notify_pardon_mock.assert_awaited_once()

    @patch("bot.exts.moderation.infraction.infractions._utils.notify_pardon")
    @patch("bot.exts.moderation.infraction.infractions.format_user")
    async def test_voice_unmute_dm_fail(self, format_user_mock, notify_pardon_mock):
        """Should add role back with ignoring, notify user and return log dictionary.."""
        self.guild.get_member.return_value = self.user
        notify_pardon_mock.return_value = False
        format_user_mock.return_value = "my-user"

        result = await self.cog.pardon_voice_mute(self.user.id, self.guild)
        self.assertEqual(result, {
            "Member": "my-user",
            "DM": "**Failed**"
        })
        notify_pardon_mock.assert_awaited_once()


class CleanBanTests(unittest.IsolatedAsyncioTestCase):
    """Tests for cleanban functionality."""

    def setUp(self):
        self.bot = MockBot()
        self.mod = MockMember(roles=[MockRole(id=7890123, position=10)])
        self.user = MockMember(roles=[MockRole(id=123456, position=1)])
        self.guild = MockGuild()
        self.ctx = MockContext(bot=self.bot, author=self.mod)
        self.cog = Infractions(self.bot)
        self.clean_cog = Clean(self.bot)
        self.management_cog = ModManagement(self.bot)

        self.cog.apply_ban = AsyncMock(return_value={"id": 42})
        self.log_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.clean_cog._clean_messages = AsyncMock(return_value=self.log_url)

    def mock_get_cog(self, enable_clean, enable_manage):
        """Mock get cog factory that allows the user to specify whether clean and manage cogs are enabled."""
        def inner(name):
            if name == "ModManagement":
                return self.management_cog if enable_manage else None
            if name == "Clean":
                return self.clean_cog if enable_clean else None
            return DEFAULT
        return inner

    async def test_cleanban_falls_back_to_native_purge_without_clean_cog(self):
        """Should fallback to native purge if the Clean cog is not available."""
        self.bot.get_cog.side_effect = self.mock_get_cog(False, False)

        self.assertIsNone(await self.cog.cleanban(self.cog, self.ctx, self.user, None, reason="FooBar"))
        self.cog.apply_ban.assert_awaited_once_with(
            self.ctx,
            self.user,
            "FooBar",
            purge_days=1,
            duration_or_expiry=None,
        )

    async def test_cleanban_doesnt_purge_messages_if_clean_cog_available(self):
        """Cleanban command should use the native purge messages if the clean cog is available."""
        self.bot.get_cog.side_effect = self.mock_get_cog(True, False)

        self.assertIsNone(await self.cog.cleanban(self.cog, self.ctx, self.user, None, reason="FooBar"))
        self.cog.apply_ban.assert_awaited_once_with(
            self.ctx,
            self.user,
            "FooBar",
            duration_or_expiry=None,
        )

    @patch("bot.exts.moderation.infraction.infractions.Age")
    async def test_cleanban_uses_clean_cog_when_available(self, mocked_age_converter):
        """Test cleanban uses the clean cog to clean messages if it's available."""
        self.bot.api_client.patch = AsyncMock()
        self.bot.get_cog.side_effect = self.mock_get_cog(True, False)

        mocked_age_converter.return_value.convert = AsyncMock(return_value="81M")
        self.assertIsNone(await self.cog.cleanban(self.cog, self.ctx, self.user, None, reason="FooBar"))

        self.clean_cog._clean_messages.assert_awaited_once_with(
            self.ctx,
            users=[self.user],
            channels="*",
            first_limit="81M",
            attempt_delete_invocation=False,
        )

    async def test_cleanban_edits_infraction_reason(self):
        """Ensure cleanban edits the ban reason with a link to the clean log."""
        self.bot.get_cog.side_effect = self.mock_get_cog(True, True)

        self.management_cog.infraction_append = AsyncMock()
        self.assertIsNone(await self.cog.cleanban(self.cog, self.ctx, self.user, None, reason="FooBar"))

        self.management_cog.infraction_append.assert_awaited_once_with(
            self.ctx,
            {"id": 42},
            None,
            reason=f"[Clean log]({self.log_url})"
        )
