import unittest


from bot.constants import Roles
from tests.helpers import MockMember, MockRole


class StreamCommandTest(unittest.IsolatedAsyncioTestCase):

    def test_checking_if_user_has_streaming_permission(self):
        """
        Test searching for video role in Member.roles
        """
        user1 = MockMember(roles=[MockRole(id=Roles.video)])
        user2 = MockMember()
        already_allowed_user1 = any(Roles.video == role.id for role in user1.roles)
        self.assertEqual(already_allowed_user1, True)

        already_allowed_user2 = any(Roles.video == role.id for role in user2.roles)
        self.assertEqual(already_allowed_user2, False)
