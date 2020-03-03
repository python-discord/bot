import unittest


from tests.helpers import MockBot, MockContext


class ModerationUtilsTests(unittest.TestCase):
    """Tests Moderation utils."""

    def setUp(self) -> None:
        self.bot = MockBot()
        self.ctx = MockContext(bot=self.bot)
