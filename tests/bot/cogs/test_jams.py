import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.cogs.jams import CodeJams, setup
from bot.constants import Roles
from tests.helpers import MockBot, MockContext, MockGuild, MockMember, MockRole, MockTextChannel


class JamCreateTeamTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `createteam` command."""

    def setUp(self):
        self.bot = MockBot()
        self.admin_role = MockRole(name="Admins", id=Roles.admins)
        self.command_user = MockMember([self.admin_role])
        self.guild = MockGuild([self.admin_role])
        self.ctx = MockContext(bot=self.bot, author=self.command_user, guild=self.guild)
        self.cog = CodeJams(self.bot)

        utils_patcher = patch("bot.cogs.jams.utils")
        self.utils_mock = utils_patcher.start()
        self.addCleanup(utils_patcher.stop)

        self.default_args = [self.cog, self.ctx, "foo"]

    async def test_too_small_amount_of_team_members_passed(self):
        """Should `ctx.send` and exit early when too small amount of members."""
        for case in (1, 2):
            with self.subTest(amount_of_members=case):
                self.cog.create_channels = AsyncMock()
                self.cog.add_roles = AsyncMock()

                self.ctx.reset_mock()
                self.utils_mock.reset_mock()
                await self.cog.createteam(*self.default_args, (MockMember() for _ in range(case)))

                self.ctx.send.assert_awaited_once()
                self.cog.create_channels.assert_not_awaited()
                self.cog.add_roles.assert_not_awaited()

    async def test_duplicate_members_provided(self):
        """Should `ctx.send` and exit early because duplicate members provided and total there is only 1 member."""
        self.cog.create_channels = AsyncMock()
        self.cog.add_roles = AsyncMock()
        member = MockMember()
        await self.cog.createteam(*self.default_args, (member for _ in range(5)))
        self.ctx.send.assert_awaited_once()
        self.cog.create_channels.assert_not_awaited()
        self.cog.add_roles.assert_not_awaited()

    async def test_result_sending(self):
        """Should call `ctx.send` when everything goes right."""
        self.cog.create_channels = AsyncMock()
        self.cog.add_roles = AsyncMock()
        members = [MockMember() for _ in range(5)]
        await self.cog.createteam(self.cog, self.ctx, "foo", members)
        self.cog.create_channels.assert_awaited_once()
        self.cog.add_roles.assert_awaited_once()
        self.ctx.send.assert_awaited_once()

    async def test_category_dont_exist(self):
        """Should create code jam category."""
        self.utils_mock.get.return_value = None
        await self.cog.get_category(self.guild)
        self.guild.create_category_channel.assert_awaited_once()
        category_overwrites = self.guild.create_category_channel.call_args[1]["overwrites"]

        self.assertFalse(category_overwrites[self.guild.default_role].read_messages)
        self.assertTrue(category_overwrites[self.guild.me].read_messages)

    async def test_category_channel_exist(self):
        """Should not try to create category channel."""
        await self.cog.get_category(self.guild)
        self.guild.create_category_channel.assert_not_awaited()

    async def test_channel_overwrites(self):
        """Should have correct permission overwrites for users and roles."""
        leader = MockMember()
        members = [leader] + [MockMember() for _ in range(4)]
        overwrites = self.cog.get_overwrites(members, self.guild)

        # Leader permission overwrites
        self.assertTrue(overwrites[leader].manage_messages)
        self.assertTrue(overwrites[leader].read_messages)
        self.assertTrue(overwrites[leader].manage_webhooks)
        self.assertTrue(overwrites[leader].connect)

        # Other members permission overwrites
        for member in members[1:]:
            self.assertTrue(overwrites[member].read_messages)
            self.assertTrue(overwrites[member].connect)

        # Everyone and verified role overwrite
        self.assertFalse(overwrites[self.guild.default_role].read_messages)
        self.assertFalse(overwrites[self.guild.default_role].connect)
        self.assertFalse(overwrites[self.guild.get_role(Roles.verified)].read_messages)
        self.assertFalse(overwrites[self.guild.get_role(Roles.verified)].connect)

    async def test_team_channels_creation(self):
        """Should create new voice and text channel for team."""
        self.utils_mock.get.return_value = "foo"
        members = [MockMember() for _ in range(5)]

        self.cog.get_overwrites = MagicMock()
        self.cog.get_category = AsyncMock()
        self.ctx.guild.create_text_channel.return_value = MockTextChannel(mention="foobar-channel")
        actual = await self.cog.create_channels(self.guild, "my-team", members)

        self.assertEqual("foobar-channel", actual)
        self.cog.get_overwrites.assert_called_once_with(members, self.guild)
        self.cog.get_category.assert_awaited_once_with(self.guild)

        self.guild.create_text_channel.assert_awaited_once_with(
            "my-team",
            overwrites=self.cog.get_overwrites.return_value,
            category=self.cog.get_category.return_value
        )
        self.guild.create_voice_channel.assert_awaited_once_with(
            "My Team",
            overwrites=self.cog.get_overwrites.return_value,
            category=self.cog.get_category.return_value
        )

    async def test_jam_roles_adding(self):
        """Should add team leader role to leader and jam role to every team member."""
        leader_role = MockRole(name="Team Leader")
        jam_role = MockRole(name="Jammer")
        self.guild.get_role.side_effect = [leader_role, jam_role]

        leader = MockMember()
        members = [leader] + [MockMember() for _ in range(4)]
        await self.cog.add_roles(self.guild, members)

        leader.add_roles.assert_any_await(leader_role)
        for member in members:
            member.add_roles.assert_any_await(jam_role)


class CodeJamSetup(unittest.TestCase):
    """Test for `setup` function of `CodeJam` cog."""

    def test_setup(self):
        """Should call `bot.add_cog`."""
        bot = MockBot()
        setup(bot)
        bot.add_cog.assert_called_once()
