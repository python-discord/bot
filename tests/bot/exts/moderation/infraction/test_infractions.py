import inspect
import textwrap
import unittest
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch

from bot.constants import Event
from bot.exts.moderation.infraction import _utils
from bot.exts.moderation.infraction.infractions import Infractions
from tests.helpers import MockBot, MockContext, MockGuild, MockMember, MockRole, MockUser, autospec


class TruncationTests(unittest.IsolatedAsyncioTestCase):
    """Tests for ban and kick command reason truncation."""

    def setUp(self):
        self.bot = MockBot()
        self.cog = Infractions(self.bot)
        self.user = MockMember(id=1234, top_role=MockRole(id=3577, position=10))
        self.target = MockMember(id=1265, top_role=MockRole(id=9876, position=0))
        self.guild = MockGuild(id=4567)
        self.ctx = MockContext(bot=self.bot, author=self.user, guild=self.guild)

    @patch("bot.exts.moderation.infraction._utils.get_active_infraction")
    @patch("bot.exts.moderation.infraction._utils.post_infraction")
    async def test_apply_ban_reason_truncation(self, post_infraction_mock, get_active_mock):
        """Should truncate reason for `ctx.guild.ban`."""
        get_active_mock.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        self.cog.apply_infraction = AsyncMock()
        self.bot.get_cog.return_value = AsyncMock()
        self.cog.mod_log.ignore = Mock()
        self.ctx.guild.ban = Mock()

        await self.cog.apply_ban(self.ctx, self.target, "foo bar" * 3000)
        self.ctx.guild.ban.assert_called_once_with(
            self.target,
            reason=textwrap.shorten("foo bar" * 3000, 512, placeholder="..."),
            delete_message_days=0
        )
        self.cog.apply_infraction.assert_awaited_once_with(
            self.ctx, {"foo": "bar"}, self.target, self.ctx.guild.ban.return_value
        )

    @patch("bot.exts.moderation.infraction._utils.post_infraction")
    async def test_apply_kick_reason_truncation(self, post_infraction_mock):
        """Should truncate reason for `Member.kick`."""
        post_infraction_mock.return_value = {"foo": "bar"}

        self.cog.apply_infraction = AsyncMock()
        self.cog.mod_log.ignore = Mock()
        self.target.kick = Mock()

        await self.cog.apply_kick(self.ctx, self.target, "foo bar" * 3000)
        self.target.kick.assert_called_once_with(reason=textwrap.shorten("foo bar" * 3000, 512, placeholder="..."))
        self.cog.apply_infraction.assert_awaited_once_with(
            self.ctx, {"foo": "bar"}, self.target, self.target.kick.return_value
        )


@patch("bot.exts.moderation.infraction.infractions.constants.Roles.voice_verified", new=123456)
class VoiceBanTests(unittest.IsolatedAsyncioTestCase):
    """Tests for voice ban related functions and commands."""

    def setUp(self):
        self.bot = MockBot()
        self.mod = MockMember(top_role=10)
        self.user = MockMember(top_role=1, roles=[MockRole(id=123456)])
        self.guild = MockGuild()
        self.ctx = MockContext(bot=self.bot, author=self.mod)
        self.cog = Infractions(self.bot)

    async def test_permanent_voice_ban(self):
        """Should call voice ban applying function without expiry."""
        self.cog.apply_voice_ban = AsyncMock()
        self.assertIsNone(await self.cog.voiceban(self.cog, self.ctx, self.user, reason="foobar"))
        self.cog.apply_voice_ban.assert_awaited_once_with(self.ctx, self.user, "foobar")

    async def test_temporary_voice_ban(self):
        """Should call voice ban applying function with expiry."""
        self.cog.apply_voice_ban = AsyncMock()
        self.assertIsNone(await self.cog.tempvoiceban(self.cog, self.ctx, self.user, "baz", reason="foobar"))
        self.cog.apply_voice_ban.assert_awaited_once_with(self.ctx, self.user, "foobar", expires_at="baz")

    async def test_voice_unban(self):
        """Should call infraction pardoning function."""
        self.cog.pardon_infraction = AsyncMock()
        self.assertIsNone(await self.cog.unvoiceban(self.cog, self.ctx, self.user))
        self.cog.pardon_infraction.assert_awaited_once_with(self.ctx, "voice_ban", self.user)

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_user_have_active_infraction(self, get_active_infraction, post_infraction_mock):
        """Should return early when user already have Voice Ban infraction."""
        get_active_infraction.return_value = {"foo": "bar"}
        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar"))
        get_active_infraction.assert_awaited_once_with(self.ctx, self.user, "voice_ban")
        post_infraction_mock.assert_not_awaited()

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_infraction_post_failed(self, get_active_infraction, post_infraction_mock):
        """Should return early when posting infraction fails."""
        self.cog.mod_log.ignore = MagicMock()
        get_active_infraction.return_value = None
        post_infraction_mock.return_value = None
        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar"))
        post_infraction_mock.assert_awaited_once()
        self.cog.mod_log.ignore.assert_not_called()

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_infraction_post_add_kwargs(self, get_active_infraction, post_infraction_mock):
        """Should pass all kwargs passed to apply_voice_ban to post_infraction."""
        get_active_infraction.return_value = None
        # We don't want that this continue yet
        post_infraction_mock.return_value = None
        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar", my_kwarg=23))
        post_infraction_mock.assert_awaited_once_with(
            self.ctx, self.user, "voice_ban", "foobar", active=True, my_kwarg=23
        )

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_mod_log_ignore(self, get_active_infraction, post_infraction_mock):
        """Should ignore Voice Verified role removing."""
        self.cog.mod_log.ignore = MagicMock()
        self.cog.apply_infraction = AsyncMock()
        self.user.remove_roles = MagicMock(return_value="my_return_value")

        get_active_infraction.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar"))
        self.cog.mod_log.ignore.assert_called_once_with(Event.member_update, self.user.id)

    async def action_tester(self, action, reason: str) -> None:
        """Helper method to test voice ban action."""
        self.assertTrue(inspect.iscoroutine(action))
        await action

        self.user.move_to.assert_called_once_with(None, reason=ANY)
        self.user.remove_roles.assert_called_once_with(self.cog._voice_verified_role, reason=reason)

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_apply_infraction(self, get_active_infraction, post_infraction_mock):
        """Should ignore Voice Verified role removing."""
        self.cog.mod_log.ignore = MagicMock()
        self.cog.apply_infraction = AsyncMock()

        get_active_infraction.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        reason = "foobar"
        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, reason))
        self.cog.apply_infraction.assert_awaited_once_with(self.ctx, {"foo": "bar"}, self.user, ANY)

        await self.action_tester(self.cog.apply_infraction.call_args[0][-1], reason)

    @patch("bot.exts.moderation.infraction.infractions._utils.post_infraction")
    @patch("bot.exts.moderation.infraction.infractions._utils.get_active_infraction")
    async def test_voice_ban_truncate_reason(self, get_active_infraction, post_infraction_mock):
        """Should truncate reason for voice ban."""
        self.cog.mod_log.ignore = MagicMock()
        self.cog.apply_infraction = AsyncMock()

        get_active_infraction.return_value = None
        post_infraction_mock.return_value = {"foo": "bar"}

        self.assertIsNone(await self.cog.apply_voice_ban(self.ctx, self.user, "foobar" * 3000))
        self.cog.apply_infraction.assert_awaited_once_with(self.ctx, {"foo": "bar"}, self.user, ANY)

        # Test action
        action = self.cog.apply_infraction.call_args[0][-1]
        await self.action_tester(action, textwrap.shorten("foobar" * 3000, 512, placeholder="..."))

    @autospec(_utils, "post_infraction", "get_active_infraction", return_value=None)
    @autospec(Infractions, "apply_infraction")
    async def test_voice_ban_user_left_guild(self, apply_infraction_mock, post_infraction_mock, _):
        """Should voice ban user that left the guild without throwing an error."""
        infraction = {"foo": "bar"}
        post_infraction_mock.return_value = {"foo": "bar"}

        user = MockUser()
        await self.cog.voiceban(self.cog, self.ctx, user, reason=None)
        post_infraction_mock.assert_called_once_with(self.ctx, user, "voice_ban", None, active=True)
        apply_infraction_mock.assert_called_once_with(self.cog, self.ctx, infraction, user, ANY)

        # Test action
        action = self.cog.apply_infraction.call_args[0][-1]
        self.assertTrue(inspect.iscoroutine(action))
        await action

    async def test_voice_unban_user_not_found(self):
        """Should include info to return dict when user was not found from guild."""
        self.guild.get_member.return_value = None
        result = await self.cog.pardon_voice_ban(self.user.id, self.guild, "foobar")
        self.assertEqual(result, {"Info": "User was not found in the guild."})

    @patch("bot.exts.moderation.infraction.infractions._utils.notify_pardon")
    @patch("bot.exts.moderation.infraction.infractions.format_user")
    async def test_voice_unban_user_found(self, format_user_mock, notify_pardon_mock):
        """Should add role back with ignoring, notify user and return log dictionary.."""
        self.guild.get_member.return_value = self.user
        notify_pardon_mock.return_value = True
        format_user_mock.return_value = "my-user"

        result = await self.cog.pardon_voice_ban(self.user.id, self.guild, "foobar")
        self.assertEqual(result, {
            "Member": "my-user",
            "DM": "Sent"
        })
        notify_pardon_mock.assert_awaited_once()

    @patch("bot.exts.moderation.infraction.infractions._utils.notify_pardon")
    @patch("bot.exts.moderation.infraction.infractions.format_user")
    async def test_voice_unban_dm_fail(self, format_user_mock, notify_pardon_mock):
        """Should add role back with ignoring, notify user and return log dictionary.."""
        self.guild.get_member.return_value = self.user
        notify_pardon_mock.return_value = False
        format_user_mock.return_value = "my-user"

        result = await self.cog.pardon_voice_ban(self.user.id, self.guild, "foobar")
        self.assertEqual(result, {
            "Member": "my-user",
            "DM": "**Failed**"
        })
        notify_pardon_mock.assert_awaited_once()
