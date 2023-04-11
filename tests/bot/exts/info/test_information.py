import textwrap
import unittest
import unittest.mock
from datetime import UTC, datetime
from textwrap import shorten

import discord

from bot import constants
from bot.exts.info import information
from bot.utils.checks import InWhitelistCheckFailure
from tests import helpers

COG_PATH = "bot.exts.info.information.Information"


class InformationCogTests(unittest.IsolatedAsyncioTestCase):
    """Tests the Information cog."""

    @classmethod
    def setUpClass(cls):
        cls.moderator_role = helpers.MockRole(name="Moderator", id=constants.Roles.moderators)

    def setUp(self):
        """Sets up fresh objects for each test."""
        self.bot = helpers.MockBot()

        self.cog = information.Information(self.bot)

        self.ctx = helpers.MockContext()
        self.ctx.author.roles.append(self.moderator_role)

    async def test_roles_command_command(self):
        """Test if the `role_info` command correctly returns the `moderator_role`."""
        self.ctx.guild.roles.append(self.moderator_role)

        self.cog.roles_info.can_run = unittest.mock.AsyncMock()
        self.cog.roles_info.can_run.return_value = True

        self.assertIsNone(await self.cog.roles_info(self.cog, self.ctx))
        self.ctx.send.assert_called_once()

        _, kwargs = self.ctx.send.call_args
        embed = kwargs.pop("embed")

        self.assertEqual(embed.title, "Role information (Total 1 role)")
        self.assertEqual(embed.colour, discord.Colour.og_blurple())
        self.assertEqual(embed.description, f"\n`{self.moderator_role.id}` - {self.moderator_role.mention}\n")

    async def test_role_info_command(self):
        """Tests the `role info` command."""
        dummy_role = helpers.MockRole(
            name="Dummy",
            id=112233445566778899,
            colour=discord.Colour.og_blurple(),
            position=10,
            members=[self.ctx.author],
            permissions=discord.Permissions(0)
        )

        admin_role = helpers.MockRole(
            name="Admins",
            id=998877665544332211,
            colour=discord.Colour.red(),
            position=3,
            members=[self.ctx.author],
            permissions=discord.Permissions(0),
        )

        self.ctx.guild.roles.extend([dummy_role, admin_role])

        self.cog.role_info.can_run = unittest.mock.AsyncMock()
        self.cog.role_info.can_run.return_value = True

        self.assertIsNone(await self.cog.role_info(self.cog, self.ctx, dummy_role, admin_role))

        self.assertEqual(self.ctx.send.call_count, 2)

        (_, dummy_kwargs), (_, admin_kwargs) = self.ctx.send.call_args_list

        dummy_embed = dummy_kwargs["embed"]
        admin_embed = admin_kwargs["embed"]

        self.assertEqual(dummy_embed.title, "Dummy info")
        self.assertEqual(dummy_embed.colour, discord.Colour.og_blurple())

        self.assertEqual(dummy_embed.fields[0].value, str(dummy_role.id))
        self.assertEqual(dummy_embed.fields[1].value, f"#{dummy_role.colour.value:0>6x}")
        self.assertEqual(dummy_embed.fields[2].value, "0.63 0.48 218")
        self.assertEqual(dummy_embed.fields[3].value, "1")
        self.assertEqual(dummy_embed.fields[4].value, "10")
        self.assertEqual(dummy_embed.fields[5].value, "0")

        self.assertEqual(admin_embed.title, "Admins info")
        self.assertEqual(admin_embed.colour, discord.Colour.red())


class UserInfractionHelperMethodTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the helper methods of the `!user` command."""

    def setUp(self):
        """Common set-up steps done before for each test."""
        self.bot = helpers.MockBot()
        self.bot.api_client.get = unittest.mock.AsyncMock()
        self.cog = information.Information(self.bot)
        self.member = helpers.MockMember(id=1234)

    async def test_user_command_helper_method_get_requests(self):
        """The helper methods should form the correct get requests."""
        test_values = (
            {
                "helper_method": self.cog.basic_user_infraction_counts,
                "expected_args": ("bot/infractions", {"hidden": "False", "user__id": str(self.member.id)}),
            },
            {
                "helper_method": self.cog.expanded_user_infraction_counts,
                "expected_args": ("bot/infractions", {"user__id": str(self.member.id)}),
            },
            {
                "helper_method": self.cog.user_nomination_counts,
                "expected_args": ("bot/nominations", {"user__id": str(self.member.id)}),
            },
        )

        for test_value in test_values:
            helper_method = test_value["helper_method"]
            endpoint, params = test_value["expected_args"]

            with self.subTest(method=helper_method, endpoint=endpoint, params=params):
                await helper_method(self.member)
                self.bot.api_client.get.assert_called_once_with(endpoint, params=params)
                self.bot.api_client.get.reset_mock()

    async def _method_subtests(self, method, test_values, default_header):
        """Helper method that runs the subtests for the different helper methods."""
        for test_value in test_values:
            api_response = test_value["api response"]
            expected_lines = test_value["expected_lines"]

            with self.subTest(method=method, api_response=api_response, expected_lines=expected_lines):
                self.bot.api_client.get.return_value = api_response

                expected_output = "\n".join(expected_lines)
                actual_output = await method(self.member)

                self.assertEqual((default_header, expected_output), actual_output)

    async def test_basic_user_infraction_counts_returns_correct_strings(self):
        """The method should correctly list both the total and active number of non-hidden infractions."""
        test_values = (
            # No infractions means zero counts
            {
                "api response": [],
                "expected_lines": ["Total: 0", "Active: 0"],
            },
            # Simple, single-infraction dictionaries
            {
                "api response": [{"type": "ban", "active": True}],
                "expected_lines": ["Total: 1", "Active: 1"],
            },
            {
                "api response": [{"type": "ban", "active": False}],
                "expected_lines": ["Total: 1", "Active: 0"],
            },
            # Multiple infractions with various `active` status
            {
                "api response": [
                    {"type": "ban", "active": True},
                    {"type": "kick", "active": False},
                    {"type": "ban", "active": True},
                    {"type": "ban", "active": False},
                ],
                "expected_lines": ["Total: 4", "Active: 2"],
            },
        )

        header = "Infractions"

        await self._method_subtests(self.cog.basic_user_infraction_counts, test_values, header)

    async def test_expanded_user_infraction_counts_returns_correct_strings(self):
        """The method should correctly list the total and active number of all infractions split by infraction type."""
        test_values = (
            {
                "api response": [],
                "expected_lines": ["No infractions"],
            },
            # Shows non-hidden inactive infraction as expected
            {
                "api response": [{"type": "kick", "active": False, "hidden": False}],
                "expected_lines": ["Kicks: 1"],
            },
            # Shows non-hidden active infraction as expected
            {
                "api response": [{"type": "mute", "active": True, "hidden": False}],
                "expected_lines": ["Mutes: 1 (1 active)"],
            },
            # Shows hidden inactive infraction as expected
            {
                "api response": [{"type": "superstar", "active": False, "hidden": True}],
                "expected_lines": ["Superstars: 1"],
            },
            # Shows hidden active infraction as expected
            {
                "api response": [{"type": "ban", "active": True, "hidden": True}],
                "expected_lines": ["Bans: 1 (1 active)"],
            },
            # Correctly displays tally of multiple infractions of mixed properties in alphabetical order
            {
                "api response": [
                    {"type": "kick", "active": False, "hidden": True},
                    {"type": "ban", "active": True, "hidden": True},
                    {"type": "superstar", "active": True, "hidden": True},
                    {"type": "mute", "active": True, "hidden": True},
                    {"type": "ban", "active": False, "hidden": False},
                    {"type": "note", "active": False, "hidden": True},
                    {"type": "note", "active": False, "hidden": True},
                    {"type": "warn", "active": False, "hidden": False},
                    {"type": "note", "active": False, "hidden": True},
                ],
                "expected_lines": [
                    "Bans: 2 (1 active)",
                    "Kicks: 1",
                    "Mutes: 1 (1 active)",
                    "Notes: 3",
                    "Superstars: 1 (1 active)",
                    "Warns: 1",
                ],
            },
        )

        header = "Infractions"

        await self._method_subtests(self.cog.expanded_user_infraction_counts, test_values, header)

    async def test_user_nomination_counts_returns_correct_strings(self):
        """The method should list the number of active and historical nominations for the user."""
        test_values = (
            {
                "api response": [],
                "expected_lines": ["No nominations"],
            },
            {
                "api response": [{"active": True}],
                "expected_lines": ["This user is **currently** nominated", "(1 nomination in total)"],
            },
            {
                "api response": [{"active": True}, {"active": False}],
                "expected_lines": ["This user is **currently** nominated", "(2 nominations in total)"],
            },
            {
                "api response": [{"active": False}],
                "expected_lines": ["This user has 1 historical nomination, but is currently not nominated."],
            },
            {
                "api response": [{"active": False}, {"active": False}],
                "expected_lines": ["This user has 2 historical nominations, but is currently not nominated."],
            },

        )

        header = "Nominations"

        await self._method_subtests(self.cog.user_nomination_counts, test_values, header)


@unittest.mock.patch("bot.exts.info.information.constants.MODERATION_CHANNELS", new=[50])
class UserEmbedTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the creation of the `!user` embed."""

    def setUp(self):
        """Common set-up steps done before for each test."""
        self.bot = helpers.MockBot()
        self.bot.api_client.get = unittest.mock.AsyncMock()
        self.cog = information.Information(self.bot)

    @unittest.mock.patch(
        f"{COG_PATH}.basic_user_infraction_counts",
        new=unittest.mock.AsyncMock(return_value=("Infractions", "basic infractions"))
    )
    @unittest.mock.patch(
        f"{COG_PATH}.user_messages",
        new=unittest.mock.AsyncMock(return_value=("Messsages", "user message count"))
    )
    async def test_create_user_embed_uses_string_representation_of_user_in_title_if_nick_is_not_available(self):
        """The embed should use the string representation of the user if they don't have a nick."""
        ctx = helpers.MockContext(channel=helpers.MockTextChannel(id=1))
        user = helpers.MockMember()
        user.public_flags = unittest.mock.MagicMock(verified_bot=False)
        user.nick = None
        user.__str__ = unittest.mock.Mock(return_value="Mr. Hemlock")
        user.colour = 0
        user.created_at = user.joined_at = datetime.now(UTC)

        embed = await self.cog.create_user_embed(ctx, user, False)

        self.assertEqual(embed.title, "Mr. Hemlock")

    @unittest.mock.patch(
        f"{COG_PATH}.basic_user_infraction_counts",
        new=unittest.mock.AsyncMock(return_value=("Infractions", "basic infractions"))
    )
    @unittest.mock.patch(
        f"{COG_PATH}.user_messages",
        new=unittest.mock.AsyncMock(return_value=("Messsages", "user message count"))
    )
    async def test_create_user_embed_uses_nick_in_title_if_available(self):
        """The embed should use the nick if it's available."""
        ctx = helpers.MockContext(channel=helpers.MockTextChannel(id=1))
        user = helpers.MockMember()
        user.public_flags = unittest.mock.MagicMock(verified_bot=False)
        user.nick = "Cat lover"
        user.__str__ = unittest.mock.Mock(return_value="Mr. Hemlock")
        user.colour = 0
        user.created_at = user.joined_at = datetime.now(UTC)

        embed = await self.cog.create_user_embed(ctx, user, False)

        self.assertEqual(embed.title, "Cat lover (Mr. Hemlock)")

    @unittest.mock.patch(
        f"{COG_PATH}.basic_user_infraction_counts",
        new=unittest.mock.AsyncMock(return_value=("Infractions", "basic infractions"))
    )
    @unittest.mock.patch(
        f"{COG_PATH}.user_messages",
        new=unittest.mock.AsyncMock(return_value=("Messsages", "user message count"))
    )
    async def test_create_user_embed_ignores_everyone_role(self):
        """Created `!user` embeds should not contain mention of the @everyone-role."""
        ctx = helpers.MockContext(channel=helpers.MockTextChannel(id=1))
        admins_role = helpers.MockRole(name="Admins")

        # A `MockMember` has the @Everyone role by default; we add the Admins to that.
        user = helpers.MockMember(roles=[admins_role], colour=100)
        user.created_at = user.joined_at = datetime.now(UTC)

        embed = await self.cog.create_user_embed(ctx, user, False)

        self.assertIn("&Admins", embed.fields[1].value)
        self.assertNotIn("&Everyone", embed.fields[1].value)

    @unittest.mock.patch(f"{COG_PATH}.expanded_user_infraction_counts", new_callable=unittest.mock.AsyncMock)
    @unittest.mock.patch(f"{COG_PATH}.user_nomination_counts", new_callable=unittest.mock.AsyncMock)
    @unittest.mock.patch(
        f"{COG_PATH}.user_messages",
        new=unittest.mock.AsyncMock(return_value=("Messsages", "user message count"))
    )
    async def test_create_user_embed_expanded_information_in_moderation_channels(
            self,
            nomination_counts,
            infraction_counts
    ):
        """The embed should contain expanded infractions and nomination info in mod channels."""
        ctx = helpers.MockContext(channel=helpers.MockTextChannel(id=50))

        moderators_role = helpers.MockRole(name="Moderators")

        infraction_counts.return_value = ("Infractions", "expanded infractions info")
        nomination_counts.return_value = ("Nominations", "nomination info")

        user = helpers.MockMember(id=314, roles=[moderators_role], colour=100)
        user.created_at = user.joined_at = datetime.fromtimestamp(1, tz=UTC)
        embed = await self.cog.create_user_embed(ctx, user, False)

        infraction_counts.assert_called_once_with(user)
        nomination_counts.assert_called_once_with(user)

        self.assertEqual(
            textwrap.dedent(f"""
                Created: {"<t:1:R>"}
                Profile: {user.mention}
                ID: {user.id}
            """).strip(),
            embed.fields[0].value
        )

        self.assertEqual(
            textwrap.dedent(f"""
                Joined: {"<t:1:R>"}
                Verified: {"True"}
                Roles: &Moderators
            """).strip(),
            embed.fields[1].value
        )

    @unittest.mock.patch(f"{COG_PATH}.basic_user_infraction_counts", new_callable=unittest.mock.AsyncMock)
    @unittest.mock.patch(f"{COG_PATH}.user_messages", new_callable=unittest.mock.AsyncMock)
    async def test_create_user_embed_basic_information_outside_of_moderation_channels(
        self,
        user_messages,
        infraction_counts,
    ):
        """The embed should contain only basic infraction data outside of mod channels."""
        ctx = helpers.MockContext(channel=helpers.MockTextChannel(id=100))

        moderators_role = helpers.MockRole(name="Moderators")

        infraction_counts.return_value = ("Infractions", "basic infractions info")
        user_messages.return_value = ("Messages", "user message counts")

        user = helpers.MockMember(id=314, roles=[moderators_role], colour=100)
        user.created_at = user.joined_at = datetime.fromtimestamp(1, tz=UTC)
        embed = await self.cog.create_user_embed(ctx, user, False)

        infraction_counts.assert_called_once_with(user)

        self.assertEqual(
            textwrap.dedent(f"""
                Created: {"<t:1:R>"}
                Profile: {user.mention}
                ID: {user.id}
            """).strip(),
            embed.fields[0].value
        )

        self.assertEqual(
            textwrap.dedent(f"""
                Joined: {"<t:1:R>"}
                Roles: &Moderators
            """).strip(),
            embed.fields[1].value
        )

        self.assertEqual(
            "user message counts",
            embed.fields[2].value
        )

        self.assertEqual(
            "basic infractions info",
            embed.fields[3].value
        )

    @unittest.mock.patch(
        f"{COG_PATH}.basic_user_infraction_counts",
        new=unittest.mock.AsyncMock(return_value=("Infractions", "basic infractions"))
    )
    @unittest.mock.patch(
        f"{COG_PATH}.user_messages",
        new=unittest.mock.AsyncMock(return_value=("Messsages", "user message count"))
    )
    async def test_create_user_embed_uses_top_role_colour_when_user_has_roles(self):
        """The embed should be created with the colour of the top role, if a top role is available."""
        ctx = helpers.MockContext()

        moderators_role = helpers.MockRole(name="Moderators")

        user = helpers.MockMember(id=314, roles=[moderators_role], colour=100)
        user.created_at = user.joined_at = datetime.now(UTC)
        embed = await self.cog.create_user_embed(ctx, user, False)

        self.assertEqual(embed.colour, discord.Colour(100))

    @unittest.mock.patch(
        f"{COG_PATH}.basic_user_infraction_counts",
        new=unittest.mock.AsyncMock(return_value=("Infractions", "basic infractions"))
    )
    @unittest.mock.patch(
        f"{COG_PATH}.user_messages",
        new=unittest.mock.AsyncMock(return_value=("Messsages", "user message count"))
    )
    async def test_create_user_embed_uses_og_blurple_colour_when_user_has_no_roles(self):
        """The embed should be created with the og blurple colour if the user has no assigned roles."""
        ctx = helpers.MockContext()

        user = helpers.MockMember(id=217, colour=discord.Colour.default())
        user.created_at = user.joined_at = datetime.now(UTC)
        embed = await self.cog.create_user_embed(ctx, user, False)

        self.assertEqual(embed.colour, discord.Colour.og_blurple())

    @unittest.mock.patch(
        f"{COG_PATH}.basic_user_infraction_counts",
        new=unittest.mock.AsyncMock(return_value=("Infractions", "basic infractions"))
    )
    @unittest.mock.patch(
        f"{COG_PATH}.user_messages",
        new=unittest.mock.AsyncMock(return_value=("Messsages", "user message count"))
    )
    async def test_create_user_embed_uses_png_format_of_user_avatar_as_thumbnail(self):
        """The embed thumbnail should be set to the user's avatar in `png` format."""
        ctx = helpers.MockContext()

        user = helpers.MockMember(id=217, colour=0)
        user.created_at = user.joined_at = datetime.now(UTC)
        user.display_avatar.url = "avatar url"
        embed = await self.cog.create_user_embed(ctx, user, False)

        self.assertEqual(embed.thumbnail.url, "avatar url")


@unittest.mock.patch("bot.exts.info.information.constants")
class UserCommandTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the `!user` command."""

    def setUp(self):
        """Set up steps executed before each test is run."""
        self.bot = helpers.MockBot()
        self.cog = information.Information(self.bot)

        self.moderator_role = helpers.MockRole(name="Moderators", id=2, position=10)
        self.flautist_role = helpers.MockRole(name="Flautists", id=3, position=2)
        self.bassist_role = helpers.MockRole(name="Bassists", id=4, position=3)

        self.author = helpers.MockMember(id=1, name="syntaxaire")
        self.moderator = helpers.MockMember(id=2, name="riffautae", roles=[self.moderator_role])
        self.target = helpers.MockMember(id=3, name="__fluzz__")

        # There's no way to mock the channel constant without deferring imports. The constant is
        # used as a default value for a parameter, which gets defined upon import.
        self.bot_command_channel = helpers.MockTextChannel(id=constants.Channels.bot_commands)

    async def test_regular_member_cannot_target_another_member(self, constants):
        """A regular user should not be able to use `!user` targeting another user."""
        constants.MODERATION_ROLES = [self.moderator_role.id]
        ctx = helpers.MockContext(author=self.author)

        await self.cog.user_info(self.cog, ctx, self.target)

        ctx.send.assert_called_once_with("You may not use this command on users other than yourself.")

    async def test_regular_member_cannot_use_command_outside_of_bot_commands(self, constants):
        """A regular user should not be able to use this command outside of bot-commands."""
        constants.MODERATION_ROLES = [self.moderator_role.id]
        constants.STAFF_ROLES = [self.moderator_role.id]
        ctx = helpers.MockContext(author=self.author, channel=helpers.MockTextChannel(id=100))

        msg = "Sorry, but you may only use this command within <#50>."
        with self.assertRaises(InWhitelistCheckFailure, msg=msg):
            await self.cog.user_info(self.cog, ctx)

    @unittest.mock.patch("bot.exts.info.information.Information.create_user_embed")
    async def test_regular_user_may_use_command_in_bot_commands_channel(self, create_embed, constants):
        """A regular user should be allowed to use `!user` targeting themselves in bot-commands."""
        constants.STAFF_ROLES = [self.moderator_role.id]
        ctx = helpers.MockContext(author=self.author, channel=self.bot_command_channel)

        await self.cog.user_info(self.cog, ctx)

        create_embed.assert_called_once_with(ctx, self.author, False)
        ctx.send.assert_called_once()

    @unittest.mock.patch("bot.exts.info.information.Information.create_user_embed")
    async def test_regular_user_can_explicitly_target_themselves(self, create_embed, _):
        """A user should target itself with `!user` when a `user` argument was not provided."""
        constants.STAFF_ROLES = [self.moderator_role.id]
        ctx = helpers.MockContext(author=self.author, channel=self.bot_command_channel)

        await self.cog.user_info(self.cog, ctx, self.author)

        create_embed.assert_called_once_with(ctx, self.author, False)
        ctx.send.assert_called_once()

    @unittest.mock.patch("bot.exts.info.information.Information.create_user_embed")
    async def test_staff_members_can_bypass_channel_restriction(self, create_embed, constants):
        """Staff members should be able to bypass the bot-commands channel restriction."""
        constants.STAFF_PARTNERS_COMMUNITY_ROLES = [self.moderator_role.id]
        ctx = helpers.MockContext(author=self.moderator, channel=helpers.MockTextChannel(id=200))

        await self.cog.user_info(self.cog, ctx)

        create_embed.assert_called_once_with(ctx, self.moderator, False)
        ctx.send.assert_called_once()

    @unittest.mock.patch("bot.exts.info.information.Information.create_user_embed")
    async def test_moderators_can_target_another_member(self, create_embed, constants):
        """A moderator should be able to use `!user` targeting another user."""
        constants.MODERATION_ROLES = [self.moderator_role.id]
        constants.STAFF_PARTNERS_COMMUNITY_ROLES = [self.moderator_role.id]
        ctx = helpers.MockContext(author=self.moderator, channel=helpers.MockTextChannel(id=50))

        await self.cog.user_info(self.cog, ctx, self.target)

        create_embed.assert_called_once_with(ctx, self.target, False)
        ctx.send.assert_called_once()


class RuleCommandTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the `!rule` command."""

    def setUp(self) -> None:
        """Set up steps executed before each test is run."""
        self.bot = helpers.MockBot()
        self.cog = information.Information(self.bot)
        self.ctx = helpers.MockContext(author=helpers.MockMember(id=1, name="Bellaluma"))
        self.full_rules = [
            (
                "First rule",
                ["first", "number_one"]
            ),
            (
                "Second rule",
                ["second", "number_two"]
            ),
            (
                "Third rule",
                ["third", "number_three"]
            )
        ]
        self.bot.api_client.get.return_value = self.full_rules

    async def test_return_none_if_one_rule_number_is_invalid(self):

        test_cases = [
            ("1 6 7 8", (6, 7, 8)),
            ("10 first", (10,)),
            ("first 10", (10,))
        ]

        for raw_user_input, extracted_rule_numbers in test_cases:
            with self.subTest(identifier=raw_user_input):
                invalid = ", ".join(
                    str(rule_number) for rule_number in extracted_rule_numbers
                    if rule_number < 1 or rule_number > len(self.full_rules))

                final_rule_numbers = await self.cog.rules(self.cog, self.ctx, args=raw_user_input)

                self.assertEqual(
                    self.ctx.send.call_args,
                    unittest.mock.call(shorten(":x: Invalid rule indices: " + invalid, 75, placeholder=" ...")))
                self.assertEqual(None, final_rule_numbers)

    async def test_return_correct_rule_numbers(self):

        test_cases = [
            ("1 2 first", {1, 2}),
            ("1 hello 2 second", {1}),
            ("second third unknown 999", {2, 3}),
        ]

        for raw_user_input, expected_matched_rule_numbers in test_cases:
            with self.subTest(identifier=raw_user_input):
                final_rule_numbers = await self.cog.rules(self.cog, self.ctx, args=raw_user_input)
                self.assertEqual(expected_matched_rule_numbers, final_rule_numbers)

    async def test_return_default_rules_when_no_input_or_no_match_are_found(self):
        test_cases = [
            ("", None),
            ("hello 2 second", None),
            ("hello 999", None),
        ]

        for raw_user_input, expected_matched_rule_numbers in test_cases:
            with self.subTest(identifier=raw_user_input):
                final_rule_numbers = await self.cog.rules(self.cog, self.ctx, args=raw_user_input)
                embed = self.ctx.send.call_args.kwargs["embed"]
                self.assertEqual(information.DEFAULT_RULES_DESCRIPTION, embed.description)
                self.assertEqual(expected_matched_rule_numbers, final_rule_numbers)
