import unittest

from bot.utils import messages


class TestMessages(unittest.TestCase):
    """Tests for functions in the `bot.utils.messages` module."""

    def test_sub_clyde(self):
        """Uppercase E's and lowercase e's are substituted with their cyrillic counterparts."""
        sub_e = "\u0435"
        sub_E = "\u0415"  # noqa: N806: Uppercase E in variable name

        test_cases = (
            (None, None),
            ("", ""),
            ("clyde", f"clyd{sub_e}"),
            ("CLYDE", f"CLYD{sub_E}"),
            ("cLyDe", f"cLyD{sub_e}"),
            ("BIGclyde", f"BIGclyd{sub_e}"),
            ("small clydeus the unholy", f"small clyd{sub_e}us the unholy"),
            ("BIGCLYDE, babyclyde", f"BIGCLYD{sub_E}, babyclyd{sub_e}"),
        )

        for username_in, username_out in test_cases:
            with self.subTest(input=username_in, expected_output=username_out):
                self.assertEqual(messages.sub_clyde(username_in), username_out)
