import unittest

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._settings import ActionSettings
from bot.exts.filtering._settings_types.actions.send_alert import SendAlert
from bot.exts.filtering.filtering import Filtering
from tests.helpers import MockBot, MockMember, MockTextChannel


class ActionDeduplicationTests(unittest.TestCase):
    def setUp(self):
        self.cog = Filtering(MockBot())

    @staticmethod
    def _make_actions(send_alert: bool) -> ActionSettings:
        actions = ActionSettings({})
        actions[SendAlert.name] = SendAlert(send_alert=send_alert)
        return actions

    @staticmethod
    def _make_context(*, author_id: int = 1, channel_id: int = 10) -> FilterContext:
        return FilterContext(
            event=Event.MESSAGE,
            author=MockMember(id=author_id),
            channel=MockTextChannel(id=channel_id),
            content="hello",
            message=None,
        )

    def test_identical_actions_in_window_are_suppressed(self):
        ctx = self._make_context()
        actions = self._make_actions(send_alert=True)

        self.assertTrue(self.cog._should_run_actions(ctx, actions))
        self.assertFalse(self.cog._should_run_actions(ctx, actions))

    def test_different_action_values_are_not_suppressed(self):
        ctx = self._make_context()
        first_actions = self._make_actions(send_alert=True)
        second_actions = self._make_actions(send_alert=False)

        self.assertTrue(self.cog._should_run_actions(ctx, first_actions))
        self.assertTrue(self.cog._should_run_actions(ctx, second_actions))

    def test_same_action_payload_for_different_authors_is_not_suppressed(self):
        first_ctx = self._make_context(author_id=1)
        second_ctx = self._make_context(author_id=2)
        actions = self._make_actions(send_alert=True)

        self.assertTrue(self.cog._should_run_actions(first_ctx, actions))
        self.assertTrue(self.cog._should_run_actions(second_ctx, actions))
