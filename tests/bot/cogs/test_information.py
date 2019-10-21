import asyncio
import textwrap
import unittest
import unittest.mock

import discord

from bot import constants
from bot.cogs import information
from tests.helpers import AsyncMock, MockBot, MockContext, MockGuild, MockMember, MockRole


class InformationCogTests(unittest.TestCase):
    """Tests the Information cog."""

    @classmethod
    def setUpClass(cls):
        cls.moderator_role = MockRole(name="Moderator", role_id=constants.Roles.moderator)

    def setUp(self):
        """Sets up fresh objects for each test."""
        self.bot = MockBot()

        self.cog = information.Information(self.bot)

        self.ctx = MockContext()
        self.ctx.author.roles.append(self.moderator_role)

    def test_roles_command_command(self):
        """Test if the `role_info` command correctly returns the `moderator_role`."""
        self.ctx.guild.roles.append(self.moderator_role)

        self.cog.roles_info.can_run = AsyncMock()
        self.cog.roles_info.can_run.return_value = True

        coroutine = self.cog.roles_info.callback(self.cog, self.ctx)

        self.assertIsNone(asyncio.run(coroutine))
        self.ctx.send.assert_called_once()

        _, kwargs = self.ctx.send.call_args
        embed = kwargs.pop('embed')

        self.assertEqual(embed.title, "Role information")
        self.assertEqual(embed.colour, discord.Colour.blurple())
        self.assertEqual(embed.description, f"`{self.moderator_role.id}` - {self.moderator_role.mention}\n")
        self.assertEqual(embed.footer.text, "Total roles: 1")

    def test_role_info_command(self):
        """Tests the `role info` command."""
        dummy_role = MockRole(
            name="Dummy",
            role_id=112233445566778899,
            colour=discord.Colour.blurple(),
            position=10,
            members=[self.ctx.author],
            permissions=discord.Permissions(0)
        )

        admin_role = MockRole(
            name="Admins",
            role_id=998877665544332211,
            colour=discord.Colour.red(),
            position=3,
            members=[self.ctx.author],
            permissions=discord.Permissions(0),
        )

        self.ctx.guild.roles.append([dummy_role, admin_role])

        self.cog.role_info.can_run = AsyncMock()
        self.cog.role_info.can_run.return_value = True

        coroutine = self.cog.role_info.callback(self.cog, self.ctx, dummy_role, admin_role)

        self.assertIsNone(asyncio.run(coroutine))

        self.assertEqual(self.ctx.send.call_count, 2)

        (_, dummy_kwargs), (_, admin_kwargs) = self.ctx.send.call_args_list

        dummy_embed = dummy_kwargs["embed"]
        admin_embed = admin_kwargs["embed"]

        self.assertEqual(dummy_embed.title, "Dummy info")
        self.assertEqual(dummy_embed.colour, discord.Colour.blurple())

        self.assertEqual(dummy_embed.fields[0].value, str(dummy_role.id))
        self.assertEqual(dummy_embed.fields[1].value, f"#{dummy_role.colour.value:0>6x}")
        self.assertEqual(dummy_embed.fields[2].value, "0.63 0.48 218")
        self.assertEqual(dummy_embed.fields[3].value, "1")
        self.assertEqual(dummy_embed.fields[4].value, "10")
        self.assertEqual(dummy_embed.fields[5].value, "0")

        self.assertEqual(admin_embed.title, "Admins info")
        self.assertEqual(admin_embed.colour, discord.Colour.red())

    @unittest.mock.patch('bot.cogs.information.time_since')
    def test_server_info_command(self, time_since_patch):
        time_since_patch.return_value = '2 days ago'

        self.ctx.guild = MockGuild(
            features=('lemons', 'apples'),
            region="The Moon",
            roles=[self.moderator_role],
            channels=[
                discord.TextChannel(
                    state={},
                    guild=self.ctx.guild,
                    data={'id': 42, 'name': 'lemons-offering', 'position': 22, 'type': 'text'}
                ),
                discord.CategoryChannel(
                    state={},
                    guild=self.ctx.guild,
                    data={'id': 5125, 'name': 'the-lemon-collection', 'position': 22, 'type': 'category'}
                ),
                discord.VoiceChannel(
                    state={},
                    guild=self.ctx.guild,
                    data={'id': 15290, 'name': 'listen-to-lemon', 'position': 22, 'type': 'voice'}
                )
            ],
            members=[
                *(MockMember(status='online') for _ in range(2)),
                *(MockMember(status='idle') for _ in range(1)),
                *(MockMember(status='dnd') for _ in range(4)),
                *(MockMember(status='offline') for _ in range(3)),
            ],
            member_count=1_234,
            icon_url='a-lemon.jpg',
        )

        coroutine = self.cog.server_info.callback(self.cog, self.ctx)
        self.assertIsNone(asyncio.run(coroutine))

        time_since_patch.assert_called_once_with(self.ctx.guild.created_at, precision='days')
        _, kwargs = self.ctx.send.call_args
        embed = kwargs.pop('embed')
        self.assertEqual(embed.colour, discord.Colour.blurple())
        self.assertEqual(
            embed.description,
            textwrap.dedent(
                f"""
                **Server information**
                Created: {time_since_patch.return_value}
                Voice region: {self.ctx.guild.region}
                Features: {', '.join(self.ctx.guild.features)}

                **Counts**
                Members: {self.ctx.guild.member_count:,}
                Roles: {len(self.ctx.guild.roles)}
                Text: 1
                Voice: 1
                Channel categories: 1

                **Members**
                {constants.Emojis.status_online} 2
                {constants.Emojis.status_idle} 1
                {constants.Emojis.status_dnd} 4
                {constants.Emojis.status_offline} 3
                """
            )
        )
        self.assertEqual(embed.thumbnail.url, 'a-lemon.jpg')
