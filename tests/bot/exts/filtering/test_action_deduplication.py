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
    def _make_context(*, author_id: int = 1, channel_id: int = 10, event: Event = Event.MESSAGE) -> FilterContext:
        return FilterContext(
            event=event,
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

    def test_same_action_payload_for_different_events_is_suppressed(self):
        """MESSAGE followed by MESSAGE_EDIT for the same user/channel/action should not double-ban."""
        msg_ctx = FilterContext(
            event=Event.MESSAGE,
            author=MockMember(id=1),
            channel=MockTextChannel(id=10),
            content="hello",
            message=None,
        )
        edit_ctx = FilterContext(
            event=Event.MESSAGE_EDIT,
            author=MockMember(id=1),
            channel=MockTextChannel(id=10),
            content="hello",
            message=None,
        )
        actions = self._make_actions(send_alert=True)

        self.assertTrue(self.cog._should_run_actions(msg_ctx, actions))
        self.assertFalse(self.cog._should_run_actions(edit_ctx, actions))

    def test_differing_additional_actions_are_still_suppressed(self):
        """Second event with no additional_actions (antispam already queued) should still be deduped."""

        async def fake_handler(ctx: FilterContext) -> None:
            pass

        first_ctx = self._make_context()
        first_ctx.additional_actions.append(fake_handler)

        second_ctx = self._make_context()  # no additional_actions

        actions = self._make_actions(send_alert=True)

        self.assertTrue(self.cog._should_run_actions(first_ctx, actions))
        self.assertFalse(self.cog._should_run_actions(second_ctx, actions))

    def test_same_action_payload_across_channels_is_suppressed(self):
        """Antispam is cross-channel; same user/action in a different channel should not double-ban."""
        first_ctx = self._make_context(channel_id=10)
        second_ctx = self._make_context(channel_id=20)
        actions = self._make_actions(send_alert=True)

        self.assertTrue(self.cog._should_run_actions(first_ctx, actions))
        self.assertFalse(self.cog._should_run_actions(second_ctx, actions))

    def test_same_action_payload_for_different_authors_is_not_suppressed(self):
        first_ctx = self._make_context(author_id=1)
        second_ctx = self._make_context(author_id=2)
        actions = self._make_actions(send_alert=True)

        self.assertTrue(self.cog._should_run_actions(first_ctx, actions))
        self.assertTrue(self.cog._should_run_actions(second_ctx, actions))
