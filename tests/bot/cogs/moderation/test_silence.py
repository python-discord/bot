import unittest

from bot.cogs.moderation.silence import FirstHash


class FirstHashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_cases = (
            (FirstHash(0, 4), FirstHash(0, 5)),
            (FirstHash("string", None), FirstHash("string", True))
        )

    def test_hashes_equal(self):
        """Check hashes equal with same first item."""

        for tuple1, tuple2 in self.test_cases:
            with self.subTest(tuple1=tuple1, tuple2=tuple2):
                self.assertEqual(hash(tuple1), hash(tuple2))

    def test_eq(self):
        """Check objects are equal with same first item."""

        for tuple1, tuple2 in self.test_cases:
            with self.subTest(tuple1=tuple1, tuple2=tuple2):
                self.assertTrue(tuple1 == tuple2)
