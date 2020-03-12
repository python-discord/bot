import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from discord import Embed, Forbidden, HTTPException, NotFound

from bot.api import ResponseCodeError
from bot.cogs.moderation import utils
from bot.constants import Colours, Icons
from tests.helpers import MockBot, MockContext, MockMember, MockUser

APPEAL_EMAIL = "appeals@pythondiscord.com"

INFRACTION_TITLE = f"Please review our rules over at {utils.RULES_URL}"
INFRACTION_APPEAL_FOOTER = f"To appeal this infraction, send an e-mail to {APPEAL_EMAIL}"
INFRACTION_AUTHOR_NAME = "Infraction information"
INFRACTION_COLOR = Colours.soft_red

INFRACTION_DESCRIPTION_TEMPLATE = (
    "\n**Type:** {type}\n"
    "**Expires:** {expires}\n"
    "**Reason:** {reason}\n"
)

PARDON_COLOR = Colours.soft_green


class ModerationUtilsTests(unittest.IsolatedAsyncioTestCase):
    """Tests Moderation utils."""

    def setUp(self):
        self.bot = MockBot()
        self.member = MockMember(id=1234)
        self.user = MockUser(id=1234)
        self.ctx = MockContext(bot=self.bot, author=self.member)

    async def test_user_has_active_infraction(self):
        """
        Test does `has_active_infraction` return call at least once `ctx.send` API get, check does return correct bool.
        """
        test_cases = [
            {
                "get_return_value": [],
                "expected_output": False,
                "infraction_nr": None
            },
            {
                "get_return_value": [{"id": 123987}],
                "expected_output": True,
                "infraction_nr": "123987"
            }
        ]

        for case in test_cases:
            with self.subTest(return_value=case["get_return_value"], expected=case["expected_output"]):
                self.bot.api_client.get.reset_mock()
                self.ctx.send.reset_mock()

                params = {
                    "active": "true",
                    "type": "ban",
                    "user__id": str(self.member.id)
                }

                self.bot.api_client.get.return_value = case["get_return_value"]

                result = await utils.has_active_infraction(self.ctx, self.member, "ban")
                self.assertEqual(result, case["expected_output"])
                self.bot.api_client.get.assert_awaited_once_with("bot/infractions", params=params)

                if result:
                    self.assertTrue(case["infraction_nr"] in self.ctx.send.call_args[0][0])
                    self.assertTrue("ban" in self.ctx.send.call_args[0][0])

    @patch("bot.cogs.moderation.utils.send_private_embed")
    async def test_notify_infraction(self, send_private_embed_mock):
        """Test does `notify_infraction` create correct embed and return correct boolean."""
        test_cases = [
            {
                "args": (self.user, "ban", "2020-02-26 09:20 (23 hours and 59 minutes)"),
                "expected_output": Embed(
                    title=INFRACTION_TITLE,
                    description=INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Ban",
                        expires="2020-02-26 09:20 (23 hours and 59 minutes)",
                        reason="No reason provided."
                    ),
                    colour=INFRACTION_COLOR,
                    url=utils.RULES_URL
                ).set_author(
                    name=INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.token_removed
                ).set_footer(text=INFRACTION_APPEAL_FOOTER),
                "send_result": True
            },
            {
                "args": (self.user, "warning", None, "Test reason."),
                "expected_output": Embed(
                    title=INFRACTION_TITLE,
                    description=INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Warning",
                        expires="N/A",
                        reason="Test reason."
                    ),
                    colour=INFRACTION_COLOR,
                    url=utils.RULES_URL
                ).set_author(
                    name=INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.token_removed
                ),
                "send_result": False
            },
            {
                "args": (self.user, "note", None, None, Icons.defcon_denied),
                "expected_output": Embed(
                    title=INFRACTION_TITLE,
                    description=INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Note",
                        expires="N/A",
                        reason="No reason provided."
                    ),
                    colour=INFRACTION_COLOR,
                    url=utils.RULES_URL
                ).set_author(
                    name=INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.defcon_denied
                ),
                "send_result": False
            },
            {
                "args": (self.user, "mute", "2020-02-26 09:20 (23 hours and 59 minutes)", "Test", Icons.defcon_denied),
                "expected_output": Embed(
                    title=INFRACTION_TITLE,
                    description=INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Mute",
                        expires="2020-02-26 09:20 (23 hours and 59 minutes)",
                        reason="Test"
                    ),
                    colour=INFRACTION_COLOR,
                    url=utils.RULES_URL
                ).set_author(
                    name=INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.defcon_denied
                ).set_footer(
                    text=INFRACTION_APPEAL_FOOTER
                ),
                "send_result": False
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]
            send = case["send_result"]

            with self.subTest(args=args, expected=expected, send=send):
                send_private_embed_mock.reset_mock()

                send_private_embed_mock.return_value = send
                result = await utils.notify_infraction(*args)

                self.assertEqual(send, result)

                embed = send_private_embed_mock.call_args[0][1]

                self.assertEqual(embed.to_dict(), expected.to_dict())

                send_private_embed_mock.assert_awaited_once_with(args[0], embed)

    @patch("bot.cogs.moderation.utils.send_private_embed")
    async def test_notify_pardon(self, send_private_embed_mock):
        """Test does `notify_pardon` create correct embed and return correct bool."""
        test_cases = [
            {
                "args": (self.user, "Test title", "Example content"),
                "icon": Icons.user_verified,
                "send_result": True
            },
            {
                "args": (self.user, "Test title", "Example content", Icons.user_update),
                "icon": Icons.user_update,
                "send_result": False
            }
        ]

        for case in test_cases:
            args = case["args"]
            send = case["send_result"]

            expected = Embed(
                description="Example content",
                colour=PARDON_COLOR).set_author(
                name="Test title",
                icon_url=case["icon"]
            )

            with self.subTest(args=args, expected=expected):
                send_private_embed_mock.reset_mock()

                send_private_embed_mock.return_value = send

                result = await utils.notify_pardon(*args)
                self.assertEqual(send, result)

                embed = send_private_embed_mock.call_args[0][1]
                self.assertEqual(embed.to_dict(), expected.to_dict())

                send_private_embed_mock.assert_awaited_once_with(args[0], embed)

    async def test_post_user(self):
        """Test does `post_user` handle errors and results correctly."""
        user = MockUser(avatar="abc", discriminator=5678, id=1234, name="Test user")
        test_cases = [
            {
                "args": (self.ctx, user),
                "post_result": "bar",
                "raise_error": False,
                "payload": {
                    "avatar_hash": "abc",
                    "discriminator": 5678,
                    "id": self.user.id,
                    "in_guild": False,
                    "name": "Test user",
                    "roles": []
                }
            },
            {
                "args": (self.ctx, self.member),
                "post_result": "foo",
                "raise_error": True,
                "payload": {
                    "avatar_hash": 0,
                    "discriminator": 0,
                    "id": self.member.id,
                    "in_guild": False,
                    "name": "Name unknown",
                    "roles": []
                }
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["post_result"]
            error = case["raise_error"]
            payload = case["payload"]

            with self.subTest(args=args, result=expected, error=error, payload=payload):
                self.bot.api_client.post.reset_mock(side_effect=True)
                self.ctx.bot.api_client.post.return_value = expected

                if error:
                    self.ctx.bot.api_client.post.side_effect = ResponseCodeError(AsyncMock(), expected)
                    err = self.ctx.bot.api_client.post.side_effect
                    err.status = 400

                result = await utils.post_user(*args)

                if error:
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result, expected)

                if not error:
                    self.bot.api_client.post.assert_awaited_once_with("bot/users", json=payload)
                else:
                    self.assertTrue(str(err.status) in self.ctx.send.call_args[0][0])

    async def test_send_private_embed(self):
        """Test does `send_private_embed` return correct bool."""
        embed = Embed(title="Test", description="Test val")

        test_cases = [
            {
                "expected_output": True,
                "raised_exception": None
            },
            {
                "expected_output": False,
                "raised_exception": HTTPException(AsyncMock(), AsyncMock())
            },
            {
                "expected_output": False,
                "raised_exception": Forbidden(AsyncMock(), AsyncMock())
            },
            {
                "expected_output": False,
                "raised_exception": NotFound(AsyncMock(), AsyncMock())
            }
        ]

        for case in test_cases:
            expected = case["expected_output"]
            raised = case["raised_exception"]

            with self.subTest(expected=expected, raised=raised):
                self.user.send.reset_mock(side_effect=True)
                self.user.send.side_effect = raised

                result = await utils.send_private_embed(self.user, embed)

                self.assertEqual(result, expected)
                if expected:
                    self.user.send.assert_awaited_once_with(embed=embed)


class TestPostInfraction(unittest.IsolatedAsyncioTestCase):
    """Tests for `post_infraction` function."""

    def setUp(self):
        self.bot = MockBot()
        self.member = MockMember(id=1234)
        self.user = MockUser(id=1234)
        self.ctx = MockContext(bot=self.bot, author=self.member)

    async def test_normal_post_infraction(self):
        """Test does `post_infraction` return correct value when no errors raise."""
        now = datetime.now()
        payload = {
            "actor": self.ctx.message.author.id,
            "hidden": True,
            "reason": "Test reason",
            "type": "ban",
            "user": self.member.id,
            "active": False,
            "expires_at": now.isoformat()
        }

        self.ctx.bot.api_client.post.return_value = "foo"
        actual = await utils.post_infraction(self.ctx, self.member, "ban", "Test reason", now, True, False)

        self.assertEqual(actual, "foo")
        self.ctx.bot.api_client.post.assert_awaited_once_with("bot/infractions", json=payload)

    async def test_unknown_error_post_infraction(self):
        """Test does `post_infraction` send info about fail to chat (`ctx.send`)."""
        self.ctx.bot.api_client.post.side_effect = ResponseCodeError(AsyncMock(), AsyncMock())
        self.ctx.bot.api_client.post.side_effect.status = 500

        actual = await utils.post_infraction(self.ctx, self.user, "ban", "Test reason")
        self.assertIsNone(actual)

        self.assertTrue("500" in self.ctx.send.call_args[0][0])

    @patch("bot.cogs.moderation.utils.post_user")
    async def test_user_not_found_none_post_infraction(self, post_user_mock):
        """Test does `post_infraction` return `None` correctly due can't create new user."""
        self.bot.api_client.post.side_effect = ResponseCodeError(MagicMock(status=400), {"user": "foo"})
        post_user_mock.return_value = None

        actual = await utils.post_infraction(self.ctx, self.user, "mute", "Test reason")
        self.assertIsNone(actual)
        post_user_mock.assert_awaited_once_with(self.ctx, self.user)

    @patch("bot.cogs.moderation.utils.post_user")
    async def test_first_fail_second_success_user_post_infraction(self, post_user_mock):
        """Test does `post_infraction` fail first time and return correct result 2nd time when new user posted."""
        payload = {
            "actor": self.ctx.message.author.id,
            "hidden": False,
            "reason": "Test reason",
            "type": "mute",
            "user": self.user.id,
            "active": True
        }

        self.bot.api_client.post.side_effect = [ResponseCodeError(MagicMock(status=400), {"user": "foo"}), "foo"]
        post_user_mock.return_value = "bar"

        actual = await utils.post_infraction(self.ctx, self.user, "mute", "Test reason")
        self.assertEqual(actual, "foo")
        self.bot.api_client.post.assert_awaited_once_with("bot/infractions", json=payload)
        post_user_mock.assert_awaited_once_with(self.ctx, self.user)
