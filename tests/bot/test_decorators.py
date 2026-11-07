import asyncio
import collections
import unittest
import unittest.mock

import arrow

from bot import constants, decorators
from bot.decorators import in_whitelist
from bot.utils.checks import InWhitelistCheckFailure
from tests import helpers

InWhitelistTestCase = collections.namedtuple("WhitelistedContextTestCase", ("kwargs", "ctx", "description"))


class InWhitelistTests(unittest.TestCase):
    """Tests for the `in_whitelist` check."""

    @classmethod
    def setUpClass(cls):
        """Set up helpers that only need to be defined once."""
        cls.bot_commands = helpers.MockTextChannel(id=123456789, category_id=123456)
        cls.help_channel = helpers.MockTextChannel(id=987654321, category_id=987654)
        cls.non_whitelisted_channel = helpers.MockTextChannel(id=666666)
        cls.dm_channel = helpers.MockDMChannel()

        cls.non_staff_member = helpers.MockMember()
        cls.staff_role = helpers.MockRole(id=121212)
        cls.staff_member = helpers.MockMember(roles=(cls.staff_role,))

        cls.channels = (cls.bot_commands.id,)
        cls.categories = (cls.help_channel.category_id,)
        cls.roles = (cls.staff_role.id,)

    def test_predicate_returns_true_for_whitelisted_context(self):
        """The predicate should return `True` if a whitelisted context was passed to it."""
        test_cases = (
            InWhitelistTestCase(
                kwargs={"channels": self.channels},
                ctx=helpers.MockContext(channel=self.bot_commands, author=self.non_staff_member),
                description="In whitelisted channels by members without whitelisted roles",
            ),
            InWhitelistTestCase(
                kwargs={"redirect": self.bot_commands.id},
                ctx=helpers.MockContext(channel=self.bot_commands, author=self.non_staff_member),
                description="`redirect` should be implicitly added to `channels`",
            ),
            InWhitelistTestCase(
                kwargs={"categories": self.categories},
                ctx=helpers.MockContext(channel=self.help_channel, author=self.non_staff_member),
                description="Whitelisted category without whitelisted role",
            ),
            InWhitelistTestCase(
                kwargs={"roles": self.roles},
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.staff_member),
                description="Whitelisted role outside of whitelisted channel/category"
            ),
            InWhitelistTestCase(
                kwargs={
                    "channels": self.channels,
                    "categories": self.categories,
                    "roles": self.roles,
                    "redirect": self.bot_commands,
                },
                ctx=helpers.MockContext(channel=self.help_channel, author=self.staff_member),
                description="Case with all whitelist kwargs used",
            ),
        )

        for test_case in test_cases:
            # patch `commands.check` with a no-op lambda that just returns the predicate passed to it
            # so we can test the predicate that was generated from the specified kwargs.
            with unittest.mock.patch("bot.decorators.commands.check", new=lambda predicate: predicate):
                predicate = in_whitelist(**test_case.kwargs)

            with self.subTest(test_description=test_case.description):
                self.assertTrue(predicate(test_case.ctx))

    def test_predicate_raises_exception_for_non_whitelisted_context(self):
        """The predicate should raise `InWhitelistCheckFailure` for a non-whitelisted context."""
        test_cases = (
            # Failing check with explicit `redirect`
            InWhitelistTestCase(
                kwargs={
                    "categories": self.categories,
                    "channels": self.channels,
                    "roles": self.roles,
                    "redirect": self.bot_commands.id,
                },
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.non_staff_member),
                description="Failing check with an explicit redirect channel",
            ),

            # Failing check with implicit `redirect`
            InWhitelistTestCase(
                kwargs={
                    "categories": self.categories,
                    "channels": self.channels,
                    "roles": self.roles,
                },
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.non_staff_member),
                description="Failing check with an implicit redirect channel",
            ),

            # Failing check without `redirect`
            InWhitelistTestCase(
                kwargs={
                    "categories": self.categories,
                    "channels": self.channels,
                    "roles": self.roles,
                    "redirect": None,
                },
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.non_staff_member),
                description="Failing check without a redirect channel",
            ),

            # Command issued in DM channel
            InWhitelistTestCase(
                kwargs={
                    "categories": self.categories,
                    "channels": self.channels,
                    "roles": self.roles,
                    "redirect": None,
                },
                ctx=helpers.MockContext(channel=self.dm_channel, author=self.dm_channel.me),
                description="Commands issued in DM channel should be rejected",
            ),
        )

        for test_case in test_cases:
            if "redirect" not in test_case.kwargs or test_case.kwargs["redirect"] is not None:
                # There are two cases in which we have a redirect channel:
                #   1. No redirect channel was passed; the default value of `bot_commands` is used
                #   2. An explicit `redirect` is set that is "not None"
                redirect_channel = test_case.kwargs.get("redirect", constants.Channels.bot_commands)
                redirect_message = f" here. Please use the <#{redirect_channel}> channel instead"
            else:
                # If an explicit `None` was passed for `redirect`, there is no redirect channel
                redirect_message = ""

            exception_message = f"You are not allowed to use that command{redirect_message}."

            # patch `commands.check` with a no-op lambda that just returns the predicate passed to it
            # so we can test the predicate that was generated from the specified kwargs.
            with unittest.mock.patch("bot.decorators.commands.check", new=lambda predicate: predicate):
                predicate = in_whitelist(**test_case.kwargs)

            with (
                self.subTest(test_description=test_case.description),
                self.assertRaisesRegex(InWhitelistCheckFailure, exception_message),
            ):
                predicate(test_case.ctx)


class SlashCommandDecoratorTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the decorators when the command is invoked as a slash command."""

    def setUp(self):
        self.interaction = helpers.MockInteraction()
        self.ctx = helpers.MockContext(interaction=self.interaction)
        self.ctx.defer = unittest.mock.AsyncMock()
        self.ctx.guild.get_channel = unittest.mock.Mock(return_value=helpers.MockTextChannel(id=555))
        self.ctx.channel = helpers.MockTextChannel(id=111)
        self.ctx.author.roles = []

    async def test_redirect_output_slash(self):
        """The command should run in a detached context sending to the destination, without touching the message."""
        called_with = []

        async def command(cog, ctx):
            called_with.append(ctx)

        wrapped = decorators.redirect_output(555)(command)

        with unittest.mock.patch(
            "bot.decorators.scheduling.create_task", side_effect=lambda coro: coro.close()
        ) as task:
            await wrapped(None, self.ctx)

        redirect_channel = self.ctx.guild.get_channel.return_value
        self.ctx.defer.assert_awaited_once_with(ephemeral=True)
        redirect_channel.send.assert_awaited_once()
        task.assert_called_once()
        self.ctx.send.assert_awaited_once()
        self.assertTrue(self.ctx.send.call_args.kwargs["ephemeral"])
        self.ctx.message.delete.assert_not_called()
        self.assertIn(redirect_channel.mention, self.ctx.send.call_args.args[0])

    async def test_redirect_output_slash_context_is_detached(self):
        """The context passed to the command should send to the destination channel, not the interaction."""
        ran = asyncio.Event()
        contexts = []

        async def command(cog, ctx):
            contexts.append(ctx)
            ran.set()

        wrapped = decorators.redirect_output(555)(command)
        await wrapped(None, self.ctx)
        await asyncio.wait_for(ran.wait(), timeout=1)

        redirected_ctx = contexts[0]
        self.assertIsNone(redirected_ctx.interaction)
        self.assertIs(redirected_ctx.channel, self.ctx.guild.get_channel.return_value)
        self.assertIs(self.ctx.interaction, self.interaction)

    async def test_ensure_future_timestamp_slash_is_ephemeral(self):
        """The past timestamp warning should only be shown to the invoking user."""
        wrapped = decorators.ensure_future_timestamp(2)(_async_command)

        await wrapped(None, self.ctx, arrow.utcnow().shift(days=-1))

        self.ctx.send.assert_awaited_once_with(":x: Provided timestamp is in the past.", ephemeral=True)

    async def test_respect_role_hierarchy_slash_is_ephemeral(self):
        """The hierarchy warning should only be shown to the invoking user."""
        target = helpers.MockMember(top_role=helpers.MockRole(position=5))
        self.ctx.author = helpers.MockMember(top_role=helpers.MockRole(position=1))
        wrapped = decorators.respect_role_hierarchy(2)(_async_command)

        await wrapped(None, self.ctx, target)

        self.ctx.send.assert_awaited_once()
        self.assertTrue(self.ctx.send.call_args.kwargs["ephemeral"])


async def _async_command(cog, ctx, arg):
    """A command callback used to test the decorators."""
