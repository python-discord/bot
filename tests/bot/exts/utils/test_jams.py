import unittest
from unittest.mock import AsyncMock, MagicMock, create_autospec

from discord import CategoryChannel
from discord.ext.commands import BadArgument

from bot.constants import Roles
from bot.exts.utils import jams
from tests.helpers import (
    MockAttachment, MockBot, MockCategoryChannel, MockContext,
    MockGuild, MockMember, MockRole, MockTextChannel
)

TEST_CSV = b"""\
Team Name,Team Member Discord ID,Team Leader
Annoyed Alligators,12345,Y
Annoyed Alligators,54321,N
Oscillating Otters,12358,Y
Oscillating Otters,74832,N
Oscillating Otters,19903,N
Annoyed Alligators,11111,N
"""


def get_mock_category(channel_count: int, name: str) -> CategoryChannel:
    """Return a mocked code jam category."""
    category = create_autospec(CategoryChannel, spec_set=True, instance=True)
    category.name = name
    category.channels = [MockTextChannel() for _ in range(channel_count)]

    return category


class JamCodejamCreateTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `codejam create` command."""

    def setUp(self):
        self.bot = MockBot()
        self.admin_role = MockRole(name="Admins", id=Roles.admins)
        self.command_user = MockMember([self.admin_role])
        self.guild = MockGuild([self.admin_role])
        self.ctx = MockContext(bot=self.bot, author=self.command_user, guild=self.guild)
        self.cog = jams.CodeJams(self.bot)

    async def test_message_without_attachments(self):
        """If no link or attachments are provided, commands.BadArgument should be raised."""
        self.ctx.message.attachments = []

        with self.assertRaises(BadArgument):
            await self.cog.create(self.cog, self.ctx, None)

    async def test_result_sending(self):
        """Should call `ctx.send` when everything goes right."""
        self.ctx.message.attachments = [MockAttachment()]
        self.ctx.message.attachments[0].read = AsyncMock()
        self.ctx.message.attachments[0].read.return_value = TEST_CSV

        team_leaders = MockRole()

        self.guild.get_member.return_value = MockMember()

        self.ctx.guild.create_role = AsyncMock()
        self.ctx.guild.create_role.return_value = team_leaders
        self.cog.create_team_channel = AsyncMock()
        self.cog.create_team_leader_channel = AsyncMock()
        self.cog.add_roles = AsyncMock()

        await self.cog.create(self.cog, self.ctx, None)

        self.cog.create_team_channel.assert_awaited()
        self.cog.create_team_leader_channel.assert_awaited_once_with(
            self.ctx.guild, team_leaders
        )
        self.ctx.send.assert_awaited_once()

    async def test_link_returning_non_200_status(self):
        """When the URL passed returns a non 200 status, it should send a message informing them."""
        self.bot.http_session.get.return_value = mock = MagicMock()
        mock.status = 404
        await self.cog.create(self.cog, self.ctx, "https://not-a-real-link.com")

        self.ctx.send.assert_awaited_once()

    async def test_category_doesnt_exist(self):
        """Should create a new code jam category."""
        subtests = (
            [],
            [get_mock_category(jams.MAX_CHANNELS, jams.CATEGORY_NAME)],
            [get_mock_category(jams.MAX_CHANNELS - 2, "other")],
        )

        self.cog.send_status_update = AsyncMock()

        for categories in subtests:
            self.cog.send_status_update.reset_mock()
            self.guild.reset_mock()
            self.guild.categories = categories

            with self.subTest(categories=categories):
                actual_category = await self.cog.get_category(self.guild)

                self.cog.send_status_update.assert_called_once()
                self.guild.create_category_channel.assert_awaited_once()
                category_overwrites = self.guild.create_category_channel.call_args[1]["overwrites"]

                self.assertFalse(category_overwrites[self.guild.default_role].read_messages)
                self.assertTrue(category_overwrites[self.guild.me].read_messages)
                self.assertEqual(self.guild.create_category_channel.return_value, actual_category)

    async def test_category_channel_exist(self):
        """Should not try to create category channel."""
        expected_category = get_mock_category(jams.MAX_CHANNELS - 2, jams.CATEGORY_NAME)
        self.guild.categories = [
            get_mock_category(jams.MAX_CHANNELS - 2, "other"),
            expected_category,
            get_mock_category(0, jams.CATEGORY_NAME),
        ]

        actual_category = await self.cog.get_category(self.guild)
        self.assertEqual(expected_category, actual_category)

    async def test_channel_overwrites(self):
        """Should have correct permission overwrites for users and roles."""
        leader = (MockMember(), True)
        members = [leader] + [(MockMember(), False) for _ in range(4)]
        overwrites = self.cog.get_overwrites(members, self.guild)

        for member, _ in members:
            self.assertTrue(overwrites[member].read_messages)

    async def test_team_channels_creation(self):
        """Should create a text channel for a team."""
        team_leaders = MockRole()
        members = [(MockMember(), True)] + [(MockMember(), False) for _ in range(5)]
        category = MockCategoryChannel()
        category.create_text_channel = AsyncMock()

        self.cog.get_overwrites = MagicMock()
        self.cog.get_category = AsyncMock()
        self.cog.get_category.return_value = category
        self.cog.add_team_leader_roles = AsyncMock()

        await self.cog.create_team_channel(self.guild, "my-team", members, team_leaders)
        self.cog.add_team_leader_roles.assert_awaited_once_with(members, team_leaders)
        self.cog.get_overwrites.assert_called_once_with(members, self.guild)
        self.cog.get_category.assert_awaited_once_with(self.guild)

        category.create_text_channel.assert_awaited_once_with(
            "my-team",
            overwrites=self.cog.get_overwrites.return_value
        )

    async def test_jam_roles_adding(self):
        """Should add team leader role to leader and jam role to every team member."""
        leader_role = MockRole(name="Team Leader")

        leader = MockMember()
        members = [(leader, True)] + [(MockMember(), False) for _ in range(4)]
        await self.cog.add_team_leader_roles(members, leader_role)

        leader.add_roles.assert_awaited_once_with(leader_role)
        for member, is_leader in members:
            if not is_leader:
                member.add_roles.assert_not_awaited()


class CodeJamSetup(unittest.TestCase):
    """Test for `setup` function of `CodeJam` cog."""

    def test_setup(self):
        """Should call `bot.add_cog`."""
        bot = MockBot()
        jams.setup(bot)
        bot.add_cog.assert_called_once()
