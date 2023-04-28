from unittest import TestCase

# noinspection PyProtectedMember
from bot.exts.utils.snekbox import _io


class SnekboxIOTests(TestCase):
    # noinspection SpellCheckingInspection
    def test_normalize_file_name(self):
        """Invalid file names should be normalized."""
        cases = [
            # ANSI escape sequences -> underscore
            (r"\u001b[31mText", "_Text"),
            # (Multiple consecutive should be collapsed to one underscore)
            (r"a\u001b[35m\u001b[37mb", "a_b"),
            # Backslash escaped chars -> underscore
            (r"\n", "_"),
            (r"\r", "_"),
            (r"A\0\tB", "A__B"),
            # Any other disallowed chars -> underscore
            (r"\\.txt", "_.txt"),
            (r"A!@#$%^&*B, C()[]{}+=D.txt", "A_B_C_D.txt"),
            (" ", "_"),
            # Normal file names should be unchanged
            ("legal_file-name.txt", "legal_file-name.txt"),
            ("_-.", "_-."),
        ]
        for name, expected in cases:
            with self.subTest(name=name, expected=expected):
                # Test function directly
                self.assertEqual(_io.normalize_discord_file_name(name), expected)
                # Test FileAttachment.to_file()
                obj = _io.FileAttachment(name, b"")
                self.assertEqual(obj.to_file().filename, expected)
