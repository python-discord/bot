import unittest

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._settings_types.bypass_roles import RoleBypass
from bot.exts.filtering._settings_types.channel_scope import ChannelScope
from bot.exts.filtering._settings_types.filter_dm import FilterDM
from bot.exts.filtering._settings_types.infraction_and_notification import (
    Infraction, InfractionAndNotification, superstar
)
from tests.helpers import MockCategoryChannel, MockDMChannel, MockMember, MockMessage, MockRole, MockTextChannel


class FilterTests(unittest.TestCase):
    """Test functionality of the Settings class and its subclasses."""

    def setUp(self) -> None:
        member = MockMember(id=123)
        channel = MockTextChannel(id=345)
        message = MockMessage(author=member, channel=channel)
        self.ctx = FilterContext(Event.MESSAGE, member, channel, "", message)

    def test_role_bypass_is_off_for_user_without_roles(self):
        """The role bypass should trigger when a user has no roles."""
        member = MockMember()
        self.ctx.author = member
        bypass_entry = RoleBypass(["123"])

        result = bypass_entry.triggers_on(self.ctx)

        self.assertTrue(result)

    def test_role_bypass_is_on_for_a_user_with_the_right_role(self):
        """The role bypass should not trigger when the user has one of its roles."""
        cases = (
            ([123], ["123"]),
            ([123, 234], ["123"]),
            ([123], ["123", "234"]),
            ([123, 234], ["123", "234"])
        )

        for user_role_ids, bypasses in cases:
            with self.subTest(user_role_ids=user_role_ids, bypasses=bypasses):
                user_roles = [MockRole(id=role_id) for role_id in user_role_ids]
                member = MockMember(roles=user_roles)
                self.ctx.author = member
                bypass_entry = RoleBypass(bypasses)

                result = bypass_entry.triggers_on(self.ctx)

                self.assertFalse(result)

    def test_context_doesnt_trigger_for_empty_channel_scope(self):
        """A filter is enabled for all channels by default."""
        channel = MockTextChannel()
        scope = ChannelScope({"disabled_channels": None, "disabled_categories": None, "enabled_channels": None})
        self.ctx.channel = channel

        result = scope.triggers_on(self.ctx)

        self.assertTrue(result)

    def test_context_doesnt_trigger_for_disabled_channel(self):
        """A filter shouldn't trigger if it's been disabled in the channel."""
        channel = MockTextChannel(id=123)
        scope = ChannelScope({"disabled_channels": ["123"], "disabled_categories": None, "enabled_channels": None})
        self.ctx.channel = channel

        result = scope.triggers_on(self.ctx)

        self.assertFalse(result)

    def test_context_doesnt_trigger_in_disabled_category(self):
        """A filter shouldn't trigger if it's been disabled in the category."""
        channel = MockTextChannel(category=MockCategoryChannel(id=456))
        scope = ChannelScope({
            "disabled_channels": None, "disabled_categories": ["456"], "enabled_channels": None
        })
        self.ctx.channel = channel

        result = scope.triggers_on(self.ctx)

        self.assertFalse(result)

    def test_context_triggers_in_enabled_channel_in_disabled_category(self):
        """A filter should trigger in an enabled channel even if it's been disabled in the category."""
        channel = MockTextChannel(id=123, category=MockCategoryChannel(id=234))
        scope = ChannelScope({"disabled_channels": None, "disabled_categories": ["234"], "enabled_channels": ["123"]})
        self.ctx.channel = channel

        result = scope.triggers_on(self.ctx)

        self.assertTrue(result)

    def test_filtering_dms_when_necessary(self):
        """A filter correctly ignores or triggers in a channel depending on the value of FilterDM."""
        cases = (
            (True, MockDMChannel(), True),
            (False, MockDMChannel(), False),
            (True, MockTextChannel(), True),
            (False, MockTextChannel(), True)
        )

        for apply_in_dms, channel, expected in cases:
            with self.subTest(apply_in_dms=apply_in_dms, channel=channel):
                filter_dms = FilterDM(apply_in_dms)
                self.ctx.channel = channel

                result = filter_dms.triggers_on(self.ctx)

                self.assertEqual(expected, result)

    def test_infraction_merge_of_same_infraction_type(self):
        """When both infractions are of the same type, the one with the longer duration wins."""
        infraction1 = InfractionAndNotification({
            "infraction_type": "mute",
            "infraction_reason": "hi",
            "infraction_duration": 10,
            "dm_content": "how",
            "dm_embed": "what is"
        })
        infraction2 = InfractionAndNotification({
            "infraction_type": "mute",
            "infraction_reason": "there",
            "infraction_duration": 20,
            "dm_content": "are you",
            "dm_embed": "your name"
        })

        result = infraction1 | infraction2

        self.assertDictEqual(
            result.to_dict(),
            {
                "infraction_type": Infraction.MUTE,
                "infraction_reason": "there",
                "infraction_duration": 20.0,
                "dm_content": "are you",
                "dm_embed": "your name",
                "_superstar": None
            }
        )

    def test_infraction_merge_of_different_infraction_types(self):
        """If there are two different infraction types, the one higher up the hierarchy should be picked."""
        infraction1 = InfractionAndNotification({
            "infraction_type": "mute",
            "infraction_reason": "hi",
            "infraction_duration": 20,
            "dm_content": "",
            "dm_embed": ""
        })
        infraction2 = InfractionAndNotification({
            "infraction_type": "ban",
            "infraction_reason": "",
            "infraction_duration": 10,
            "dm_content": "there",
            "dm_embed": ""
        })

        result = infraction1 | infraction2

        self.assertDictEqual(
            result.to_dict(),
            {
                "infraction_type": Infraction.BAN,
                "infraction_reason": "",
                "infraction_duration": 10.0,
                "dm_content": "there",
                "dm_embed": "",
                "_superstar": None
            }
        )

    def test_infraction_merge_with_a_superstar(self):
        """If there is a superstar infraction, it should be added to a separate field."""
        infraction1 = InfractionAndNotification({
            "infraction_type": "mute",
            "infraction_reason": "hi",
            "infraction_duration": 20,
            "dm_content": "there",
            "dm_embed": ""
        })
        infraction2 = InfractionAndNotification({
            "infraction_type": "superstar",
            "infraction_reason": "hello",
            "infraction_duration": 10,
            "dm_content": "you",
            "dm_embed": ""
        })

        result = infraction1 | infraction2

        self.assertDictEqual(
            result.to_dict(),
            {
                "infraction_type": Infraction.MUTE,
                "infraction_reason": "hi",
                "infraction_duration": 20.0,
                "dm_content": "there",
                "dm_embed": "",
                "_superstar": superstar("hello", 10.0)
            }
        )

    def test_merge_two_superstar_infractions(self):
        """When two superstar infractions are merged, the infraction type remains a superstar."""
        infraction1 = InfractionAndNotification({
            "infraction_type": "superstar",
            "infraction_reason": "hi",
            "infraction_duration": 20,
            "dm_content": "",
            "dm_embed": ""
        })
        infraction2 = InfractionAndNotification({
            "infraction_type": "superstar",
            "infraction_reason": "",
            "infraction_duration": 10,
            "dm_content": "there",
            "dm_embed": ""
        })

        result = infraction1 | infraction2

        self.assertDictEqual(
            result.to_dict(),
            {
                "infraction_type": Infraction.SUPERSTAR,
                "infraction_reason": "hi",
                "infraction_duration": 20.0,
                "dm_content": "",
                "dm_embed": "",
                "_superstar": None
            }
        )

    def test_merge_a_voiceban_and_a_superstar_with_another_superstar(self):
        """An infraction with a superstar merged with a superstar should combine under `_superstar`."""
        infraction1 = InfractionAndNotification({
            "infraction_type": "voice ban",
            "infraction_reason": "hi",
            "infraction_duration": 20,
            "dm_content": "hello",
            "dm_embed": ""
        })
        infraction2 = InfractionAndNotification({
            "infraction_type": "superstar",
            "infraction_reason": "bla",
            "infraction_duration": 10,
            "dm_content": "there",
            "dm_embed": ""
        })
        infraction3 = InfractionAndNotification({
            "infraction_type": "superstar",
            "infraction_reason": "blabla",
            "infraction_duration": 20,
            "dm_content": "there",
            "dm_embed": ""
        })

        result = infraction1 | infraction2 | infraction3

        self.assertDictEqual(
            result.to_dict(),
            {
                "infraction_type": Infraction.VOICE_BAN,
                "infraction_reason": "hi",
                "infraction_duration": 20,
                "dm_content": "hello",
                "dm_embed": "",
                "_superstar": superstar("blabla", 20)
            }
        )
