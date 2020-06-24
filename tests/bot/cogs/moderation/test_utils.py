import textwrap
import unittest
from collections import namedtuple
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

from discord import Embed, Forbidden, HTTPException, NotFound

from bot.api import ResponseCodeError
from bot.cogs.moderation import utils
from bot.constants import Colours, Icons
from tests.helpers import MockBot, MockContext, MockMember, MockUser

INFRACTION_DESCRIPTION_TEMPLATE = (
    "\n**Type:** {type}\n"
    "**Expires:** {expires}\n"
    "**Reason:** {reason}\n"
)


class ModerationUtilsTests(unittest.IsolatedAsyncioTestCase):
    """Tests Moderation utils."""

    def setUp(self):
        self.bot = MockBot()
        self.member = MockMember(id=1234)
        self.user = MockUser(id=1234)
        self.ctx = MockContext(bot=self.bot, author=self.member)

    async def test_user_get_active_infraction(self):
        """
        Should request the API for active infractions and return infraction if the user has one or `None` otherwise.

        A message should be sent to the context indicating a user already has an infraction, if that's the case.
        """
        test_case = namedtuple("test_case", ["get_return_value", "expected_output", "infraction_nr", "send_msg"])
        test_cases = [
            test_case([], None, None, True),
            test_case([{"id": 123987}], {"id": 123987}, "123987", False),
            test_case([{"id": 123987}], {"id": 123987}, "123987", True)
        ]

        for case in test_cases:
            with self.subTest(return_value=case.get_return_value, expected=case.expected_output):
                self.bot.api_client.get.reset_mock()
                self.ctx.send.reset_mock()

                params = {
                    "active": "true",
                    "type": "ban",
                    "user__id": str(self.member.id)
                }

                self.bot.api_client.get.return_value = case.get_return_value

                result = await utils.get_active_infraction(self.ctx, self.member, "ban", send_msg=case.send_msg)
                self.assertEqual(result, case.expected_output)
                self.bot.api_client.get.assert_awaited_once_with("bot/infractions", params=params)

                if case.send_msg and case.get_return_value:
                    self.ctx.send.assert_awaited_once()
                    self.assertTrue(case.infraction_nr in self.ctx.send.call_args[0][0])
                    self.assertTrue("ban" in self.ctx.send.call_args[0][0])
                else:
                    self.ctx.send.assert_not_awaited()

    @patch("bot.cogs.moderation.utils.send_private_embed")
    async def test_notify_infraction(self, send_private_embed_mock):
        """
        Should send an embed of a certain format as a DM and return `True` if DM successful.

        Appealable infractions should have the appeal message in the embed's footer.
        """
        test_cases = [
            {
                "args": (self.user, "ban", "2020-02-26 09:20 (23 hours and 59 minutes)"),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=textwrap.shorten(INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Ban",
                        expires="2020-02-26 09:20 (23 hours and 59 minutes)",
                        reason="No reason provided."
                    ), width=2048, placeholder="..."),
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.token_removed
                ).set_footer(text=utils.INFRACTION_APPEAL_FOOTER),
                "send_result": True
            },
            {
                "args": (self.user, "warning", None, "Test reason."),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=textwrap.shorten(INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Warning",
                        expires="N/A",
                        reason="Test reason."
                    ), width=2048, placeholder="..."),
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.token_removed
                ),
                "send_result": False
            },
            {
                "args": (self.user, "note", None, None, Icons.defcon_denied),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=textwrap.shorten(INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Note",
                        expires="N/A",
                        reason="No reason provided."
                    ), width=2048, placeholder="..."),
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.defcon_denied
                ),
                "send_result": False
            },
            {
                "args": (self.user, "mute", "2020-02-26 09:20 (23 hours and 59 minutes)", "Test", Icons.defcon_denied),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=textwrap.shorten(INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Mute",
                        expires="2020-02-26 09:20 (23 hours and 59 minutes)",
                        reason="Test"
                    ), width=2048, placeholder="..."),
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.defcon_denied
                ).set_footer(text=utils.INFRACTION_APPEAL_FOOTER),
                "send_result": False
            },
            {
                "args": (self.user, "mute", None, "foo bar" * 4000, Icons.defcon_denied),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=textwrap.shorten(INFRACTION_DESCRIPTION_TEMPLATE.format(
                        type="Mute",
                        expires="N/A",
                        reason="foo bar" * 4000
                    ), width=2048, placeholder="..."),
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.defcon_denied
                ).set_footer(text=utils.INFRACTION_APPEAL_FOOTER),
                "send_result": True
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
        """Should send an embed of a certain format as a DM and return `True` if DM successful."""
        test_case = namedtuple("test_case", ["args", "icon", "send_result"])
        test_cases = [
            test_case((self.user, "Test title", "Example content"), Icons.user_verified, True),
            test_case((self.user, "Test title", "Example content", Icons.user_update), Icons.user_update, False)
        ]

        for case in test_cases:
            expected = Embed(
                description="Example content",
                colour=Colours.soft_green
            ).set_author(
                name="Test title",
                icon_url=case.icon
            )

            with self.subTest(args=case.args, expected=expected):
                send_private_embed_mock.reset_mock()

                send_private_embed_mock.return_value = case.send_result

                result = await utils.notify_pardon(*case.args)
                self.assertEqual(case.send_result, result)

                embed = send_private_embed_mock.call_args[0][1]
                self.assertEqual(embed.to_dict(), expected.to_dict())

                send_private_embed_mock.assert_awaited_once_with(case.args[0], embed)

    @patch("bot.cogs.moderation.utils.log")
    async def test_post_user(self, log_mock):
        """Should POST a new user and return the response if successful or otherwise send an error message."""
        user = MockUser(discriminator=5678, id=1234, name="Test user")
        some_mock = MagicMock(discriminator=3333)
        test_cases = [
            {
                "user": user,
                "post_result": "bar",
                "raise_error": None,
                "payload": {
                    "discriminator": 5678,
                    "id": self.user.id,
                    "in_guild": False,
                    "name": "Test user",
                    "roles": []
                }
            },
            {
                "user": self.member,
                "post_result": "foo",
                "raise_error": ResponseCodeError(MagicMock(status=400), "foo"),
                "payload": {
                    "discriminator": 0,
                    "id": self.member.id,
                    "in_guild": False,
                    "name": "Name unknown",
                    "roles": []
                }
            },
            {
                "user": some_mock,
                "post_result": "bar",
                "raise_error": None,
                "payload": {
                    "discriminator": some_mock.discriminator,
                    "id": some_mock.id,
                    "in_guild": False,
                    "name": some_mock.name,
                    "roles": []
                }
            }
        ]

        for case in test_cases:
            test_user = case["user"]
            expected = case["post_result"]
            error = case["raise_error"]
            payload = case["payload"]

            with self.subTest(user=test_user, result=expected, error=error, payload=payload):
                log_mock.reset_mock()
                self.bot.api_client.post.reset_mock(side_effect=True)
                self.ctx.bot.api_client.post.return_value = expected

                self.ctx.bot.api_client.post.side_effect = error

                result = await utils.post_user(self.ctx, test_user)

                if error:
                    self.assertIsNone(result)
                else:
                    self.assertEqual(result, expected)

                if not error:
                    self.bot.api_client.post.assert_awaited_once_with("bot/users", json=payload)
                else:
                    self.ctx.send.assert_awaited_once()
                    self.assertTrue(str(error.status) in self.ctx.send.call_args[0][0])

                if isinstance(test_user, MagicMock):
                    log_mock.debug.assert_called_once()
                else:
                    log_mock.debug.assert_not_called()

    async def test_send_private_embed(self):
        """Should DM the user and return `True` on success or `False` on failure."""
        embed = Embed(title="Test", description="Test val")

        test_case = namedtuple("test_case", ["expected_output", "raised_exception"])
        test_cases = [
            test_case(True, None),
            test_case(False, HTTPException(AsyncMock(), AsyncMock())),
            test_case(False, Forbidden(AsyncMock(), AsyncMock())),
            test_case(False, NotFound(AsyncMock(), AsyncMock()))
        ]

        for case in test_cases:
            with self.subTest(expected=case.expected_output, raised=case.raised_exception):
                self.user.send.reset_mock(side_effect=True)
                self.user.send.side_effect = case.raised_exception

                result = await utils.send_private_embed(self.user, embed)

                self.assertEqual(result, case.expected_output)
                if case.expected_output:
                    self.user.send.assert_awaited_once_with(embed=embed)


class TestPostInfraction(unittest.IsolatedAsyncioTestCase):
    """Tests for the `post_infraction` function."""

    def setUp(self):
        self.bot = MockBot()
        self.member = MockMember(id=1234)
        self.user = MockUser(id=1234)
        self.ctx = MockContext(bot=self.bot, author=self.member)

    async def test_normal_post_infraction(self):
        """Should return response from POST request if there are no errors."""
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
        """Should send an error message to chat when a non-400 error occurs."""
        self.ctx.bot.api_client.post.side_effect = ResponseCodeError(AsyncMock(), AsyncMock())
        self.ctx.bot.api_client.post.side_effect.status = 500

        actual = await utils.post_infraction(self.ctx, self.user, "ban", "Test reason")
        self.assertIsNone(actual)

        self.assertTrue("500" in self.ctx.send.call_args[0][0])

    @patch("bot.cogs.moderation.utils.post_user", return_value=None)
    async def test_user_not_found_none_post_infraction(self, post_user_mock):
        """Should abort and return `None` when a new user fails to be posted."""
        self.bot.api_client.post.side_effect = ResponseCodeError(MagicMock(status=400), {"user": "foo"})

        actual = await utils.post_infraction(self.ctx, self.user, "mute", "Test reason")
        self.assertIsNone(actual)
        post_user_mock.assert_awaited_once_with(self.ctx, self.user)

    @patch("bot.cogs.moderation.utils.post_user", return_value="bar")
    async def test_first_fail_second_success_user_post_infraction(self, post_user_mock):
        """Should post the user if they don't exist, POST infraction again, and return the response if successful."""
        payload = {
            "actor": self.ctx.message.author.id,
            "hidden": False,
            "reason": "Test reason",
            "type": "mute",
            "user": self.user.id,
            "active": True
        }

        self.bot.api_client.post.side_effect = [ResponseCodeError(MagicMock(status=400), {"user": "foo"}), "foo"]

        actual = await utils.post_infraction(self.ctx, self.user, "mute", "Test reason")
        self.assertEqual(actual, "foo")
        self.bot.api_client.post.assert_has_awaits([call("bot/infractions", json=payload)] * 2)
        post_user_mock.assert_awaited_once_with(self.ctx, self.user)
