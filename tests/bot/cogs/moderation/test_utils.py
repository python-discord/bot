import unittest
from datetime import datetime
from typing import Union
from unittest.mock import AsyncMock, patch

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
                "get_return_value": [{"id": 1}],
                "expected_output": True,
                "infraction_nr": "**#1**"
            }
        ]

        for case in test_cases:
            with self.subTest(return_value=case["get_return_value"], expected=case["expected_output"]):
                self.bot.api_client.get.reset_mock()
                self.ctx.send.reset_mock()

                self.bot.api_client.get.return_value = case["get_return_value"]

                result = await utils.has_active_infraction(self.ctx, self.member, "ban")
                self.assertEqual(result, case["expected_output"])
                self.bot.api_client.get.assert_awaited_once_with("bot/infractions", params={
                    "active": "true",
                    "type": "ban",
                    "user__id": str(self.member.id)
                })

                if result:
                    self.assertTrue(case["infraction_nr"] in self.ctx.send.call_args[0][0])
                    self.assertTrue("ban" in self.ctx.send.call_args[0][0])

    @patch("bot.cogs.moderation.utils.send_private_embed")
    async def test_notify_infraction(self, send_private_embed_mock):
        """Test does `notify_infraction` create correct embed and return correct boolean."""
        test_cases = [
            {
                "args": (self.user, "ban", "2020-02-26 09:20 (23 hours and 59 minutes)"),
                "expected_output": {
                    "description": INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Ban",
                        expires="2020-02-26 09:20 (23 hours and 59 minutes)",
                        reason="No reason provided."
                    ),
                    "icon_url": Icons.token_removed,
                    "footer": INFRACTION_APPEAL_FOOTER,
                },
                "send_result": True,
                "send_raise": None
            },
            {
                "args": (self.user, "warning", None, "Test reason."),
                "expected_output": {
                    "description": INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Warning",
                        expires="N/A",
                        reason="Test reason."
                    ),
                    "icon_url": Icons.token_removed,
                    "footer": Embed.Empty
                },
                "send_result": False,
                "send_raise": Forbidden(AsyncMock(), AsyncMock())
            },
            {
                "args": (self.user, "note", None, None, Icons.defcon_denied),
                "expected_output": {
                    "description": INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Note",
                        expires="N/A",
                        reason="No reason provided."
                    ),
                    "icon_url": Icons.defcon_denied,
                    "footer": Embed.Empty
                },
                "send_result": False,
                "send_raise": NotFound(AsyncMock(), AsyncMock())
            },
            {
                "args": (self.user, "mute", "2020-02-26 09:20 (23 hours and 59 minutes)", "Test", Icons.defcon_denied),
                "expected_output": {
                    "description": INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Mute",
                        expires="2020-02-26 09:20 (23 hours and 59 minutes)",
                        reason="Test"
                    ),
                    "icon_url": Icons.defcon_denied,
                    "footer": INFRACTION_APPEAL_FOOTER
                },
                "send_result": False,
                "send_raise": HTTPException(AsyncMock(), AsyncMock())
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]
            send, send_raise = case["send_result"], case["send_raise"]

            with self.subTest(args=args, expected=expected, send=send, send_raise=send_raise):
                if send_raise:
                    self.ctx.send.side_effect = send_raise

                send_private_embed_mock.return_value = send

                result = await utils.notify_infraction(*args)

                self.assertEqual(send, result)

                embed = send_private_embed_mock.call_args[0][1]

                self.assertEqual(embed.title, INFRACTION_TITLE)
                self.assertEqual(embed.colour.value, INFRACTION_COLOR)
                self.assertEqual(embed.url, utils.RULES_URL)
                self.assertEqual(embed.author.name, INFRACTION_AUTHOR_NAME)
                self.assertEqual(embed.author.url, utils.RULES_URL)
                self.assertEqual(embed.author.icon_url, expected["icon_url"])
                self.assertEqual(embed.footer.text, expected["footer"])
                self.assertEqual(embed.description, expected["description"])

                send_private_embed_mock.assert_awaited_once_with(args[0], embed)

                self.ctx.send.reset_mock(side_effect=True)
                send_private_embed_mock.reset_mock()

    @patch("bot.cogs.moderation.utils.send_private_embed")
    async def test_notify_pardon(self, send_private_embed_mock):
        """Test does `notify_pardon` create correct embed and return correct bool."""
        test_cases = [
            {
                "args": (self.user, "Test title", "Example content"),
                "expected_output": {
                    "description": "Example content",
                    "title": "Test title",
                    "icon_url": Icons.user_verified
                },
                "send_result": True,
                "send_raise": None
            },
            {
                "args": (self.user, "Test title 1", "Example content 1", Icons.user_update),
                "expected_output": {
                    "description": "Example content 1",
                    "title": "Test title 1",
                    "icon_url": Icons.user_update
                },
                "send_result": False,
                "send_raise": NotFound(AsyncMock(), AsyncMock())
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]
            send, send_raise = case["send_result"], case["send_raise"]

            with self.subTest(args=args, expected=expected):
                if send_raise:
                    self.ctx.send.side_effect = send_raise

                send_private_embed_mock.return_value = send

                result = await utils.notify_pardon(*args)

                self.assertEqual(send, result)

                embed = send_private_embed_mock.call_args[0][1]

                self.assertEqual(embed.description, expected["description"])
                self.assertEqual(embed.colour.value, PARDON_COLOR)
                self.assertEqual(embed.author.name, expected["title"])
                self.assertEqual(embed.author.icon_url, expected["icon_url"])

                send_private_embed_mock.assert_awaited_once_with(args[0], embed)

                self.ctx.send.reset_mock(side_effect=True)
                send_private_embed_mock.reset_mock()

    async def test_post_user(self):
        """Test does `post_user` handle errors and results correctly."""
        test_cases = [
            {
                "args": (self.ctx, self.user),
                "post_result": [
                    {
                        "id": 1234,
                        "avatar": "test",
                        "name": "Test",
                        "discriminator": 1234,
                        "roles": [
                            1234,
                            5678
                        ],
                        "in_guild": False
                    }
                ],
                "raise_error": False,
                "payload": {
                    "avatar_hash": getattr(self.user, "avatar", 0),
                    "discriminator": int(getattr(self.user, "discriminator", 0)),
                    "id": self.user.id,
                    "in_guild": False,
                    "name": getattr(self.user, "name", "Name unknown"),
                    "roles": []
                }
            },
            {
                "args": (self.ctx, self.user),
                "post_result": [
                    {
                        "id": 1234,
                        "avatar": "test",
                        "name": "Test",
                        "discriminator": 1234,
                        "roles": [
                            1234,
                            5678
                        ],
                        "in_guild": False
                    }
                ],
                "raise_error": True,
                "payload": {
                    "avatar_hash": getattr(self.user, "avatar", 0),
                    "discriminator": int(getattr(self.user, "discriminator", 0)),
                    "id": self.user.id,
                    "in_guild": False,
                    "name": getattr(self.user, "name", "Name unknown"),
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
                self.ctx.bot.api_client.post.return_value = expected

                if error:
                    self.ctx.bot.api_client.post.side_effect = ResponseCodeError(AsyncMock(), expected)

                result = await utils.post_user(*args)

                if error:
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result, expected)

                if not error:
                    self.bot.api_client.post.assert_awaited_once_with("bot/users", json=payload)

                self.bot.api_client.post.reset_mock(side_effect=True)

    async def test_send_private_embed(self):
        """Test does `send_private_embed` return correct bool."""
        test_cases = [
            {
                "args": (self.user, Embed(title="Test", description="Test val")),
                "expected_output": True,
                "raised_exception": None
            },
            {
                "args": (self.user, Embed(title="Test", description="Test val")),
                "expected_output": False,
                "raised_exception": HTTPException(AsyncMock(), AsyncMock())
            },
            {
                "args": (self.user, Embed(title="Test", description="Test val")),
                "expected_output": False,
                "raised_exception": Forbidden(AsyncMock(), AsyncMock())
            },
            {
                "args": (self.user, Embed(title="Test", description="Test val")),
                "expected_output": False,
                "raised_exception": NotFound(AsyncMock(), AsyncMock())
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]
            raised: Union[Forbidden, HTTPException, NotFound, None] = case["raised_exception"]

            with self.subTest(args=args, expected=expected, raised=raised):
                if raised:
                    self.user.send.side_effect = raised

                result = await utils.send_private_embed(*args)

                self.assertEqual(result, expected)
                if expected:
                    args[0].send.assert_awaited_once_with(embed=args[1])

                self.user.send.reset_mock(side_effect=True)

    @patch("bot.cogs.moderation.utils.post_user")
    async def test_post_infraction(self, post_user_mock):
        """Test does `post_infraction` call functions correctly and return `None` or `Dict`."""
        now = datetime.now()
        test_cases = [
            {
                "args": (self.ctx, self.member, "ban", "Test Ban"),
                "expected_output": [
                    {
                        "id": 1,
                        "inserted_at": "2018-11-22T07:24:06.132307Z",
                        "expires_at": "5018-11-20T15:52:00Z",
                        "active": True,
                        "user": 1234,
                        "actor": 1234,
                        "type": "ban",
                        "reason": "Test Ban",
                        "hidden": False
                    }
                ],
                "raised_error": None,
                "payload": {
                    "actor": self.ctx.message.author.id,
                    "hidden": False,
                    "reason": "Test Ban",
                    "type": "ban",
                    "user": self.member.id,
                    "active": True
                }
            },
            {
                "args": (self.ctx, self.member, "note", "Test Ban"),
                "expected_output": None,
                "raised_error": ResponseCodeError(AsyncMock(), AsyncMock()),
                "payload": {
                    "actor": self.ctx.message.author.id,
                    "hidden": False,
                    "reason": "Test Ban",
                    "type": "note",
                    "user": self.member.id,
                    "active": True
                }
            },
            {
                "args": (self.ctx, self.member, "mute", "Test Ban"),
                "expected_output": None,
                "raised_error": ResponseCodeError(AsyncMock(status=400), {'user': 1234}),
                "payload": {
                    "actor": self.ctx.message.author.id,
                    "hidden": False,
                    "reason": "Test Ban",
                    "type": "mute",
                    "user": self.member.id,
                    "active": True
                }
            },
            {
                "args": (self.ctx, self.member, "ban", "Test Ban", now, True, False),
                "expected_output": [
                    {
                        "id": 1,
                        "inserted_at": "2018-11-22T07:24:06.132307Z",
                        "expires_at": "5018-11-20T15:52:00Z",
                        "active": True,
                        "user": 1234,
                        "actor": 1234,
                        "type": "ban",
                        "reason": "Test Ban",
                        "hidden": False
                    }
                ],
                "raised_error": None,
                "payload": {
                    "actor": self.ctx.message.author.id,
                    "hidden": True,
                    "reason": "Test Ban",
                    "type": "ban",
                    "user": self.member.id,
                    "active": False,
                    "expires_at": now.isoformat()
                }
            },
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]
            raised = case["raised_error"]
            payload = case["payload"]

            with self.subTest(args=args, expected=expected, raised=raised, payload=payload):
                self.ctx.bot.api_client.post.reset_mock(side_effect=True)
                post_user_mock.reset_mock()

                if raised:
                    self.ctx.bot.api_client.post.side_effect = raised

                post_user_mock.return_value = "foo"

                self.ctx.bot.api_client.post.return_value = expected

                result = await utils.post_infraction(*args)

                self.assertEqual(result, expected)

                if not raised:
                    self.bot.api_client.post.assert_awaited_once_with("bot/infractions", json=payload)

                if hasattr(raised, "status") and hasattr(raised, "response_json"):
                    if raised.status == 400 and "user" in raised.response_json:
                        post_user_mock.assert_awaited_once_with(args[0], args[1])
