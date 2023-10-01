import unittest
from collections import namedtuple
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from discord import Embed, Forbidden, HTTPException, NotFound
from pydis_core.site_api import ResponseCodeError

from bot.constants import Colours, Icons
from bot.exts.moderation.infraction import _utils as utils
from tests.helpers import MockBot, MockContext, MockMember, MockUser


class ModerationUtilsTests(unittest.IsolatedAsyncioTestCase):
    """Tests Moderation utils."""

    def setUp(self):
        patcher = patch("bot.instance", new=MockBot())
        self.bot = patcher.start()
        self.addCleanup(patcher.stop)

        self.member = MockMember(id=1234)
        self.user = MockUser(id=1234)
        self.ctx = MockContext(bot=self.bot, author=self.member)

    async def test_post_user(self):
        """Should POST a new user and return the response if successful or otherwise send an error message."""
        user = MockUser(discriminator=5678, id=1234, name="Test user")
        not_user = MagicMock(discriminator=3333, id=5678, name="Wrong user")
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
                "user": not_user,
                "post_result": "bar",
                "raise_error": None,
                "payload": {
                    "discriminator": not_user.discriminator,
                    "id": not_user.id,
                    "in_guild": False,
                    "name": not_user.name,
                    "roles": []
                }
            }
        ]

        for case in test_cases:
            user = case["user"]
            post_result = case["post_result"]
            raise_error = case["raise_error"]
            payload = case["payload"]

            with self.subTest(user=user, post_result=post_result, raise_error=raise_error, payload=payload):
                self.bot.api_client.post.reset_mock(side_effect=True)
                self.ctx.bot.api_client.post.return_value = post_result

                self.ctx.bot.api_client.post.side_effect = raise_error

                result = await utils.post_user(self.ctx, user)

                if raise_error:
                    self.assertIsNone(result)
                    self.ctx.send.assert_awaited_once()
                    self.assertIn(str(raise_error.status), self.ctx.send.call_args[0][0])
                else:
                    self.assertEqual(result, post_result)
                    self.bot.api_client.post.assert_awaited_once_with("bot/users", json=payload)

    async def test_get_active_infraction(self):
        """
        Should request the API for active infractions and return infraction if the user has one or `None` otherwise.

        A message should be sent to the context indicating a user already has an infraction, if that's the case.
        """
        test_case = namedtuple("test_case", ["get_return_value", "expected_output", "infraction_nr", "send_msg"])
        test_cases = [
            test_case([], None, None, True),
            test_case([{"id": 123987, "type": "ban"}], {"id": 123987, "type": "ban"}, "123987", False),
            test_case([{"id": 123987, "type": "ban"}], {"id": 123987, "type": "ban"}, "123987", True)
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
                    sent_message = self.ctx.send.call_args[0][0]
                    self.assertIn(case.infraction_nr, sent_message)
                    self.assertIn("ban", sent_message)
                else:
                    self.ctx.send.assert_not_awaited()

    @unittest.skip("Current time needs to be patched so infraction duration is correct.")
    @patch("bot.exts.moderation.infraction._utils.send_private_embed")
    async def test_send_infraction_embed(self, send_private_embed_mock):
        """
        Should send an embed of a certain format as a DM and return `True` if DM successful.

        Appealable infractions should have the appeal message in the embed's footer.
        """
        test_cases = [
            {
                "args": (
                    dict(id=0, type="ban", reason=None, expires_at=datetime(2020, 2, 26, 9, 20, tzinfo=UTC)),
                    self.user,
                ),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=utils.INFRACTION_DESCRIPTION_NOT_WARNING_TEMPLATE.format(
                        type="Ban",
                        expires="2020-02-26 09:20 (23 hours and 59 minutes)",
                        reason="No reason provided."
                    ) + utils.INFRACTION_APPEAL_SERVER_FOOTER,
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.user_ban
                ),
                "send_result": True
            },
            {
                "args": (dict(id=0, type="warning", reason="Test reason.", expires_at=None), self.user),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=utils.INFRACTION_DESCRIPTION_NOT_WARNING_TEMPLATE.format(
                        type="Warning",
                        expires="N/A",
                        reason="Test reason."
                    ) + utils.INFRACTION_APPEAL_MODMAIL_FOOTER,
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.user_warn
                ),
                "send_result": False
            },
            # Note that this test case asserts that the DM that *would* get sent to the user is formatted
            # correctly, even though that message is deliberately never sent.
            {
                "args": (dict(id=0, type="note", reason=None, expires_at=None), self.user),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=utils.INFRACTION_DESCRIPTION_NOT_WARNING_TEMPLATE.format(
                        type="Note",
                        expires="N/A",
                        reason="No reason provided."
                    ) + utils.INFRACTION_APPEAL_MODMAIL_FOOTER,
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.user_warn
                ),
                "send_result": False
            },
            {
                "args": (
                    dict(id=0, type="mute", reason="Test", expires_at=datetime(2020, 2, 26, 9, 20, tzinfo=UTC)),
                    self.user,
                ),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=utils.INFRACTION_DESCRIPTION_NOT_WARNING_TEMPLATE.format(
                        type="Mute",
                        expires="2020-02-26 09:20 (23 hours and 59 minutes)",
                        reason="Test"
                    ) + utils.INFRACTION_APPEAL_MODMAIL_FOOTER,
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.user_mute
                ),
                "send_result": False
            },
            {
                "args": (dict(id=0, type="mute", reason="foo bar" * 4000, expires_at=None), self.user),
                "expected_output": Embed(
                    title=utils.INFRACTION_TITLE,
                    description=utils.INFRACTION_DESCRIPTION_NOT_WARNING_TEMPLATE.format(
                        type="Mute",
                        expires="N/A",
                        reason="foo bar" * 4000
                    )[:4093-utils.LONGEST_EXTRAS] + "..." + utils.INFRACTION_APPEAL_MODMAIL_FOOTER,
                    colour=Colours.soft_red,
                    url=utils.RULES_URL
                ).set_author(
                    name=utils.INFRACTION_AUTHOR_NAME,
                    url=utils.RULES_URL,
                    icon_url=Icons.user_mute
                ),
                "send_result": True
            }
        ]

        for case in test_cases:
            with self.subTest(args=case["args"], expected=case["expected_output"], send=case["send_result"]):
                send_private_embed_mock.reset_mock()

                send_private_embed_mock.return_value = case["send_result"]
                result = await utils.notify_infraction(*case["args"])

                self.assertEqual(case["send_result"], result)

                embed = send_private_embed_mock.call_args[0][1]

                self.assertEqual(embed.to_dict(), case["expected_output"].to_dict())

                send_private_embed_mock.assert_awaited_once_with(case["args"][1], embed)

    @patch("bot.exts.moderation.infraction._utils.send_private_embed")
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
        now = datetime.now(UTC)
        expected = {
            "actor": self.ctx.author.id,
            "hidden": True,
            "reason": "Test reason",
            "type": "ban",
            "user": self.member.id,
            "active": False,
            "expires_at": now.isoformat(),
            "dm_sent": False,
        }

        self.ctx.bot.api_client.post.return_value = "foo"
        actual = await utils.post_infraction(self.ctx, self.member, "ban", "Test reason", now, True, False)
        self.assertEqual(actual, "foo")
        self.ctx.bot.api_client.post.assert_awaited_once()

        # Since `last_applied` is based on current time, just check if expected is a subset of payload
        payload: dict = self.ctx.bot.api_client.post.await_args_list[0].kwargs["json"]
        self.assertEqual(payload, payload | expected)

    async def test_unknown_error_post_infraction(self):
        """Should send an error message to chat when a non-400 error occurs."""
        self.ctx.bot.api_client.post.side_effect = ResponseCodeError(AsyncMock(), AsyncMock())
        self.ctx.bot.api_client.post.side_effect.status = 500

        actual = await utils.post_infraction(self.ctx, self.user, "ban", "Test reason")
        self.assertIsNone(actual)

        self.assertTrue("500" in self.ctx.send.call_args[0][0])

    @patch("bot.exts.moderation.infraction._utils.post_user", return_value=None)
    async def test_user_not_found_none_post_infraction(self, post_user_mock):
        """Should abort and return `None` when a new user fails to be posted."""
        self.bot.api_client.post.side_effect = ResponseCodeError(MagicMock(status=400), {"user": "foo"})

        actual = await utils.post_infraction(self.ctx, self.user, "mute", "Test reason")
        self.assertIsNone(actual)
        post_user_mock.assert_awaited_once_with(self.ctx, self.user)

    @patch("bot.exts.moderation.infraction._utils.post_user", return_value="bar")
    async def test_first_fail_second_success_user_post_infraction(self, post_user_mock):
        """Should post the user if they don't exist, POST infraction again, and return the response if successful."""
        expected = {
            "actor": self.ctx.author.id,
            "hidden": False,
            "reason": "Test reason",
            "type": "mute",
            "user": self.user.id,
            "active": True,
            "dm_sent": False,
        }

        self.bot.api_client.post.side_effect = [ResponseCodeError(MagicMock(status=400), {"user": "foo"}), "foo"]
        actual = await utils.post_infraction(self.ctx, self.user, "mute", "Test reason")
        self.assertEqual(actual, "foo")
        await_args = self.bot.api_client.post.await_args_list
        self.assertEqual(len(await_args), 2, "Expected 2 awaits")

        # Since `last_applied` is based on current time, just check if expected is a subset of payload
        for args in await_args:
            payload: dict = args.kwargs["json"]
            self.assertEqual(payload, payload | expected)

        post_user_mock.assert_awaited_once_with(self.ctx, self.user)
