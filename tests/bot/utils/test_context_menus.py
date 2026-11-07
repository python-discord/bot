import unittest
from unittest import mock

from discord import app_commands
from discord.ext import commands

from bot.errors import LockedResourceError
from bot.utils import context_menus
from bot.utils.checks import InWhitelistCheckFailure
from tests import helpers


class AuthoriseCommandTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `authorise_command`."""

    @staticmethod
    def _command(*checks, cog_check=None) -> mock.Mock:
        command = mock.Mock(spec=commands.Command)
        command.parents = []
        command.checks = list(checks)
        command._prepare_cooldowns = mock.Mock()
        command.call_before_hooks = mock.AsyncMock()
        command.name = "test"
        return command

    async def test_passing_command_returns_context(self):
        command = self._command()
        interaction, ctx = helpers.make_menu_interaction(command)

        with mock.patch.object(commands.Command, "can_run", mock.AsyncMock(return_value=True)):
            result = await context_menus.authorise_command(interaction, "test")

        self.assertIs(result, ctx)
        self.assertIs(ctx.command, command)
        command._prepare_cooldowns.assert_called_once_with(ctx)
        command.call_before_hooks.assert_awaited_once_with(ctx)

    async def test_failing_check_is_denied(self):
        command = self._command()
        interaction, _ = helpers.make_menu_interaction(command)

        with (
            mock.patch.object(commands.Command, "can_run", mock.AsyncMock(return_value=False)),
            self.assertRaises(context_menus.ContextMenuDenied),
        ):
            await context_menus.authorise_command(interaction, "test")

        command._prepare_cooldowns.assert_not_called()

    async def test_whitelist_failure_message_is_kept(self):
        command = self._command()
        interaction, _ = helpers.make_menu_interaction(command)

        with (
            mock.patch.object(commands.Command, "can_run", mock.AsyncMock(side_effect=InWhitelistCheckFailure(5))),
            self.assertRaises(context_menus.ContextMenuDenied) as cm,
        ):
            await context_menus.authorise_command(interaction, "test")

        self.assertIn("<#5>", cm.exception.message)

    async def test_parent_checks_run_first(self):
        parent = self._command()
        command = self._command()
        command.parents = [parent]
        interaction, _ = helpers.make_menu_interaction(command)

        can_run = mock.AsyncMock(side_effect=[False])
        with (
            mock.patch.object(commands.Command, "can_run", can_run),
            self.assertRaises(context_menus.ContextMenuDenied),
        ):
            await context_menus.authorise_command(interaction, "test")

        self.assertEqual(can_run.await_args_list, [mock.call(parent, mock.ANY)])

    async def test_cooldown_is_denied(self):
        command = self._command()
        command.call_before_hooks.side_effect = commands.CommandOnCooldown(mock.Mock(), 12.0, commands.BucketType.user)
        interaction, _ = helpers.make_menu_interaction(command)

        with (
            mock.patch.object(commands.Command, "can_run", mock.AsyncMock(return_value=True)),
            self.assertRaises(context_menus.ContextMenuDenied) as cm,
        ):
            await context_menus.authorise_command(interaction, "test")

        self.assertIn("12", cm.exception.message)


class ErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `context_menu_error_handler`."""

    @staticmethod
    def _interaction(*, done: bool) -> helpers.MockInteraction:
        interaction = helpers.MockInteraction()
        interaction.response = mock.Mock(is_done=mock.Mock(return_value=done), send_message=mock.AsyncMock())
        interaction.followup = mock.Mock(send=mock.AsyncMock())
        return interaction

    async def test_denied_is_ephemeral(self):
        interaction = self._interaction(done=False)

        error = app_commands.CommandInvokeError(mock.Mock(), context_menus.ContextMenuDenied("Nope"))
        await context_menus.context_menu_error_handler(interaction, error)

        interaction.response.send_message.assert_awaited_once_with(":x: Nope", ephemeral=True)

    async def test_followup_used_when_already_responded(self):
        interaction = self._interaction(done=True)

        await context_menus.context_menu_error_handler(interaction, context_menus.ContextMenuDenied("Nope"))

        interaction.followup.send.assert_awaited_once_with(":x: Nope", ephemeral=True)

    async def test_locked_resource(self):
        interaction = self._interaction(done=False)

        await context_menus.context_menu_error_handler(interaction, LockedResourceError("user", 1))

        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(interaction.response.send_message.await_args.kwargs["ephemeral"])
