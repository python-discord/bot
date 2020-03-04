import unittest
from typing import Union
from unittest.mock import AsyncMock

from discord import Embed, Forbidden, HTTPException, NotFound

from bot.api import ResponseCodeError
from bot.cogs.moderation.utils import (
    has_active_infraction, notify_infraction, notify_pardon, post_user, send_private_embed
)
from bot.constants import Colours, Icons
from tests.helpers import MockBot, MockContext, MockMember, MockUser

RULES_URL = "https://pythondiscord.com/pages/rules"
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
        self.bot.api_client.get = AsyncMock()

    async def test_user_has_active_infraction_true(self):
        """Test does `has_active_infraction` return that user have active infraction."""
        self.bot.api_client.get.return_value = [{
            "id": 1,
            "inserted_at": "2018-11-22T07:24:06.132307Z",
            "expires_at": "5018-11-20T15:52:00Z",
            "active": True,
            "user": 1234,
            "actor": 1234,
            "type": "ban",
            "reason": "Test",
            "hidden": False
        }]
        self.assertTrue(await has_active_infraction(self.ctx, self.member, "ban"), "User should have active infraction")

    async def test_user_has_active_infraction_false(self):
        """Test does `has_active_infraction` return that user don't have active infractions."""
        self.bot.api_client.get.return_value = []
        self.assertFalse(
            await has_active_infraction(self.ctx, self.member, "ban"),
            "User shouldn't have active infraction"
        )

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
                "raised_exception": HTTPException
            },
            {
                "args": (self.user, Embed(title="Test", description="Test val")),
                "expected_output": False,
                "raised_exception": Forbidden
            },
            {
                "args": (self.user, Embed(title="Test", description="Test val")),
                "expected_output": False,
                "raised_exception": NotFound
            }
        ]

        for case in test_cases:
            args = case["args"]
            expected = case["expected_output"]
            raised: Union[Forbidden, HTTPException, NotFound, None] = case["raised_exception"]

            with self.subTest(args=args, expected=expected, raised=raised):
                if raised:
                    self.user.send.side_effect = raised(AsyncMock(), AsyncMock())

                result = await send_private_embed(*args)

                self.assertEqual(result, expected)
