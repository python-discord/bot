import unittest
from datetime import datetime
from typing import Union
from unittest.mock import AsyncMock

from discord import Embed, Forbidden, HTTPException, NotFound

from bot.api import ResponseCodeError
from bot.cogs.moderation.utils import (
    RULES_URL, has_active_infraction, notify_infraction, notify_pardon, post_infraction, post_user, send_private_embed
)
from bot.constants import Colours, Icons
from tests.helpers import MockBot, MockContext, MockMember, MockUser

APPEAL_EMAIL = "appeals@pythondiscord.com"

INFRACTION_TITLE = f"Please review our rules over at {RULES_URL}"
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
        """Test does `has_active_infraction` return correct value."""
        test_cases = [
            {
                "args": (self.ctx, self.member, "ban"),
                "get_return_value": [],
                "expected_output": False,
                "get_call": {
                    "active": "true",
                    "type": "ban",
                    "user__id": str(self.member.id)
                },
                "send_params": None
            },
            {
                "args": (self.ctx, self.member, "ban"),
                "get_return_value": [{
                    "id": 1,
                    "inserted_at": "2018-11-22T07:24:06.132307Z",
                    "expires_at": "5018-11-20T15:52:00Z",
                    "active": True,
                    "user": 1234,
                    "actor": 1234,
                    "type": "ban",
                    "reason": "Test",
                    "hidden": False
                }],
                "expected_output": True,
                "get_call": {
                    "active": "true",
                    "type": "ban",
                    "user__id": str(self.member.id)
                },
                "send_params": (
                    f":x: According to my records, this user already has a ban infraction. "
                    f"See infraction **#1**."
                )
            }
        ]

        for case in test_cases:
            args = case["args"]
            return_value = case["get_return_value"]
            expected = case["expected_output"]
            get = case["get_call"]
            send_vals = case["send_params"]

            with self.subTest(args=args, return_value=return_value, expected=expected, get=get, send_vals=send_vals):
                self.bot.api_client.get.return_value = return_value

                result = await has_active_infraction(*args)
                self.assertEqual(result, expected)
                self.bot.api_client.get.assert_awaited_once_with("bot/infractions", params=get)

                if result:
                    self.ctx.send.assert_awaited_once_with(send_vals)

                self.bot.api_client.get.reset_mock()
                self.ctx.send.reset_mock()

    async def test_notify_infraction(self):
        """Test does `notify_infraction` create correct embed."""
        test_cases = [
            {
                "args": (self.user, "ban", "2020-02-26 09:20 (23 hours and 59 minutes)"),
                "expected_output": {
                    "description": INFRACTION_DESCRIPTION_TEMPLATE.format(**{
                        "type": "Ban",
                        "expires": "2020-02-26 09:20 (23 hours and 59 minutes)",
                        "reason": "No reason provided."
                    }),
                    "icon_url": Icons.token_removed,
                    "footer": INFRACTION_APPEAL_FOOTER
                }
            },
            {
                "args": (self.user, "warning", None, "Test reason."),
                "expected_output": {
                    "description": INFRACTION_DESCRIPTION_TEMPLATE.format(**{
                        "type": "Warning",
                        "expires": "N/A",
                        "reason": "Test reason."
                    }),
                    "icon_url": Icons.token_removed,
                    "footer": Embed.Empty
                }
            },
            {
                "args": (self.user, "note", None, None, Icons.defcon_denied),
                "expected_output": {
                    "description": INFRACTION_DESCRIPTION_TEMPLATE.format(**{
                        "type": "Note",
                        "expires": "N/A",
                        "reason": "No reason provided."
                    }),
                    "icon_url": Icons.defcon_denied,
                    "footer": Embed.Empty
                }
            },
            {
                "args": (self.user, "mute", "2020-02-26 09:20 (23 hours and 59 minutes)", "Test", Icons.defcon_denied),
                "expected_output": {
                    "description": INFRACTION_DESCRIPTION_TEMPLATE.format(**{
                        "type": "Mute",
                        "expires": "2020-02-26 09:20 (23 hours and 59 minutes)",
                        "reason": "Test"
                    }),
                    "icon_url": Icons.defcon_denied,
                    "footer": INFRACTION_APPEAL_FOOTER
                }
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]

            with self.subTest(args=args, expected=expected):
                await notify_infraction(*args)

                embed: Embed = self.user.send.call_args[1]["embed"]

                self.assertEqual(embed.title, INFRACTION_TITLE)
                self.assertEqual(embed.colour.value, INFRACTION_COLOR)
                self.assertEqual(embed.url, RULES_URL)
                self.assertEqual(embed.author.name, INFRACTION_AUTHOR_NAME)
                self.assertEqual(embed.author.url, RULES_URL)
                self.assertEqual(embed.author.icon_url, expected["icon_url"])
                self.assertEqual(embed.footer.text, expected["footer"])
                self.assertEqual(embed.description, expected["description"])

    async def test_notify_pardon(self):
        """Test does `notify_pardon` create correct embed."""
        test_cases = [
            {
                "args": (self.user, "Test title", "Example content"),
                "expected_output": {
                    "description": "Example content",
                    "title": "Test title",
                    "icon_url": Icons.user_verified
                }
            },
            {
                "args": (self.user, "Test title 1", "Example content 1", Icons.user_update),
                "expected_output": {
                    "description": "Example content 1",
                    "title": "Test title 1",
                    "icon_url": Icons.user_update
                }
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]

            with self.subTest(args=args, expected=expected):
                await notify_pardon(*args)

                embed: Embed = self.user.send.call_args[1]["embed"]

                self.assertEqual(embed.description, expected["description"])
                self.assertEqual(embed.colour.value, PARDON_COLOR)
                self.assertEqual(embed.author.name, expected["title"])
                self.assertEqual(embed.author.icon_url, expected["icon_url"])

    async def test_post_user(self):
        """Test does `post_user` work correctly."""
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
                        "in_guild": True
                    }
                ],
                "raise_error": False
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
                        "in_guild": True
                    }
                ],
                "raise_error": True
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["post_result"]
            error = case["raise_error"]

            with self.subTest(args=args, result=expected, error=error):
                self.ctx.bot.api_client.post.return_value = expected

                if error:
                    self.ctx.bot.api_client.post.side_effect = ResponseCodeError(AsyncMock(), expected)

                result = await post_user(*args)

                if error:
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result, expected)

    async def test_send_private_embed(self):
        """Test does `send_private_embed` return correct value."""
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

                result = await send_private_embed(*args)

                self.assertEqual(result, expected)

                self.user.send.reset_mock(side_effect=True)

    async def test_post_infraction(self):
        """Test does `post_infraction` return correct value."""
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
                "raised_error": None
            },
            {
                "args": (self.ctx, self.member, "note", "Test Ban"),
                "expected_output": None,
                "raised_error": ResponseCodeError(AsyncMock(), AsyncMock())
            },
            {
                "args": (self.ctx, self.member, "mute", "Test Ban"),
                "expected_output": None,
                "raised_error": ResponseCodeError(AsyncMock(), {'user': 1234})
            },
            {
                "args": (self.ctx, self.member, "ban", "Test Ban", datetime.now()),
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
                "raised_error": None
            },
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]
            raised = case["raised_error"]

            with self.subTest(args=args, expected=expected, raised=raised):
                if raised:
                    self.ctx.bot.api_client.post.side_effect = raised

                self.ctx.bot.api_client.post.return_value = expected

                result = await post_infraction(*args)

                self.assertEqual(result, expected)

                self.ctx.bot.api_client.post.reset_mock(side_effect=True)
