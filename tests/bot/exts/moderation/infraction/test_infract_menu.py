import unittest
from unittest import mock

import discord

from bot.constants import MODERATION_ROLES, Roles
from bot.exts.moderation.infraction import _menu
from bot.exts.moderation.infraction.infractions import Infractions
from bot.utils.context_menus import ContextMenuDenied
from tests import helpers


class InfractMenuTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the Infract user context menu."""

    def setUp(self):
        self.cog = Infractions(helpers.MockBot())
        # Commands only have their cog set once the cog is added to a bot.
        for action in _menu.INFRACTION_ACTIONS.values():
            getattr(self.cog, action.command).cog = self.cog
        self.target = helpers.MockMember(roles=[helpers.MockRole(position=1)])

    def _interaction(self, role_ids=(MODERATION_ROLES[0],), top_role_position=10):
        interaction, ctx = helpers.make_menu_interaction(None, role_ids=role_ids)
        interaction.client.get_command.side_effect = lambda name: getattr(self.cog, name)
        interaction.user.top_role = helpers.MockRole(position=top_role_position)
        interaction.response = mock.Mock(send_message=mock.AsyncMock(), send_modal=mock.AsyncMock())
        ctx.defer = mock.AsyncMock()
        ctx.invoke = mock.AsyncMock()
        return interaction, ctx

    def test_menu_is_guild_only_user_menu(self):
        menu = self.cog.infract_menu
        self.assertEqual(menu.type, discord.AppCommandType.user)
        self.assertTrue(menu.guild_only)
        self.assertLessEqual(len(menu.name), 32)

    def test_actions_are_commands_with_slash_commands(self):
        for key, action in _menu.INFRACTION_ACTIONS.items():
            with self.subTest(action=key):
                command = getattr(self.cog, action.command)
                self.assertIsNotNone(command.app_command)

    async def test_moderator_is_offered_the_infractions(self):
        interaction, _ = self._interaction()

        await self.cog._infract_menu_callback(interaction, self.target)

        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.await_args.kwargs
        self.assertTrue(kwargs["ephemeral"])
        self.assertIsInstance(kwargs["view"], _menu.InfractionActionView)

    async def test_non_moderator_is_denied(self):
        interaction, _ = self._interaction(role_ids=(Roles.helpers,))

        with self.assertRaises(ContextMenuDenied):
            await self.cog._infract_menu_callback(interaction, self.target)

        interaction.response.send_message.assert_not_called()

    async def test_target_with_equal_or_higher_top_role_is_denied(self):
        for position in (10, 11):
            with self.subTest(target_position=position):
                interaction, _ = self._interaction(top_role_position=10)
                target = helpers.MockMember(roles=[helpers.MockRole(position=position)])

                with self.assertRaises(ContextMenuDenied):
                    await self.cog._infract_menu_callback(interaction, target)

                interaction.response.send_message.assert_not_called()

    async def test_choosing_an_infraction_opens_a_modal_for_it(self):
        expected_duration_field = {"warn": False, "ban": False, "timeout": True, "tempban": True}
        for key, has_duration in expected_duration_field.items():
            with self.subTest(action=key):
                interaction, ctx = self._interaction()
                view = _menu.InfractionActionView(self.cog, ctx, self.target)
                view.select._values = [key]

                await view.on_select(interaction)

                modal = interaction.response.send_modal.await_args.args[0]
                self.assertEqual(modal.action, _menu.INFRACTION_ACTIONS[key])
                self.assertEqual(modal.duration is not None, has_duration)

    async def test_choosing_an_infraction_is_gated_on_its_command(self):
        interaction, ctx = self._interaction()
        view = _menu.InfractionActionView(self.cog, ctx, self.target)
        view.select._values = ["ban"]

        with (
            mock.patch.object(_menu, "authorise_context", mock.AsyncMock(side_effect=ContextMenuDenied)) as authorise,
            self.assertRaises(ContextMenuDenied),
        ):
            await view.on_select(interaction)

        authorise.assert_awaited_once_with(ctx, "ban")
        interaction.response.send_modal.assert_not_called()

    async def test_every_select_option_has_an_action(self):
        _, ctx = self._interaction()
        view = _menu.InfractionActionView(self.cog, ctx, self.target)

        self.assertEqual({o.value for o in view.select.options}, set(_menu.INFRACTION_ACTIONS))
        self.assertLessEqual(len(view.select.options), 25)

    def _modal(self, key, ctx, duration="", reason=""):
        modal = _menu.InfractionModal(self.cog, ctx, _menu.INFRACTION_ACTIONS[key], self.target)
        if modal.duration is not None:
            modal.duration._value = duration
        modal.reason._value = reason
        return modal

    async def test_submitting_runs_the_command_after_deferring(self):
        interaction, ctx = self._interaction()
        modal = self._modal("kick", ctx, reason="spam")
        calls = mock.Mock()
        ctx.defer.side_effect = lambda *a, **k: calls.defer()
        ctx.invoke.side_effect = lambda *a, **k: calls.invoke(*a, **k)

        await modal.on_submit(interaction)

        self.assertIs(ctx.interaction, interaction)
        self.assertEqual([c[0] for c in calls.mock_calls], ["defer", "invoke"])
        ctx.invoke.assert_awaited_once_with(self.cog.kick, self.target, reason="spam")

    async def test_submitting_without_a_reason(self):
        interaction, ctx = self._interaction()
        modal = self._modal("warn", ctx)

        await modal.on_submit(interaction)

        ctx.invoke.assert_awaited_once_with(self.cog.warn, self.target, reason=None)

    async def test_submitting_with_a_duration(self):
        interaction, ctx = self._interaction()
        modal = self._modal("tempban", ctx, duration="3d", reason="raid")

        await modal.on_submit(interaction)

        args = ctx.invoke.await_args.args
        self.assertEqual(args[:2], (self.cog.tempban, self.target))
        self.assertEqual(args[2].days, 3)
        self.assertEqual(ctx.invoke.await_args.kwargs, {"reason": "raid"})

    async def test_optional_duration_may_be_empty(self):
        interaction, ctx = self._interaction()
        modal = self._modal("timeout", ctx)

        await modal.on_submit(interaction)

        ctx.invoke.assert_awaited_once_with(self.cog.timeout, self.target, None, reason=None)

    async def test_invalid_duration_is_rejected_ephemerally(self):
        interaction, ctx = self._interaction()
        modal = self._modal("tempban", ctx, duration="soon")
        interaction.response.send_message = mock.AsyncMock()

        await modal.on_submit(interaction)

        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(interaction.response.send_message.await_args.kwargs["ephemeral"])
        ctx.defer.assert_not_called()
        ctx.invoke.assert_not_called()

    async def test_submitting_after_losing_the_role_is_denied(self):
        interaction, ctx = self._interaction()
        modal = self._modal("ban", ctx)
        ctx.author.roles = []

        with self.assertRaises(ContextMenuDenied):
            await modal.on_submit(interaction)

        ctx.defer.assert_not_called()
        ctx.invoke.assert_not_called()
