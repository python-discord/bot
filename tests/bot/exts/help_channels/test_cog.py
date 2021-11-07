import unittest
from unittest.mock import patch

from bot.exts.help_channels import _cog
from tests.helpers import MockBot, MockMember, MockRedisCache


class HelpChannelsCogTest(unittest.IsolatedAsyncioTestCase):
    """Test the HelpChannels cog."""

    def setUp(self):
        self.bot = MockBot()
        self.cog = _cog.HelpChannels(self.bot)

    @patch("bot.exts.help_channels._cog._caches")
    async def test_sync_cooldown_roles(self, _caches):
        # Given
        claimant_member = MockMember(id="345")
        non_claimant_member = MockMember(id="456")

        _caches.claimants = MockRedisCache()
        _caches.claimants.to_dict.return_value = {"123": claimant_member.id}

        self.bot.get_guild.return_value.get_role.return_value.members = [
            claimant_member,
            non_claimant_member,
        ]

        # When
        await self.cog.sync_cooldown_roles()

        # Then
        claimant_member.remove_roles.assert_not_called()
        non_claimant_member.remove_roles.assert_called()
