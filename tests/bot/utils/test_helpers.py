import unittest

from bot.utils import helpers


class TestHelpers(unittest.TestCase):
    """Tests for the helper functions in the `bot.utils.helpers` module."""

    def test_find_nth_occurrence_returns_index(self):
        """Test if `find_nth_occurrence` returns the index correctly when substring is found."""
        test_values = (
            ("hello", "l", 1, 2),
            ("hello", "l", 2, 3),
            ("hello world", "world", 1, 6),
            ("hello world", " ", 1, 5),
            ("hello world", "o w", 1, 4)
        )

        for string, substring, n, expected_index in test_values:
            with self.subTest(string=string, substring=substring, n=n):
                index = helpers.find_nth_occurrence(string, substring, n)
                self.assertEqual(index, expected_index)

    def test_find_nth_occurrence_returns_none(self):
        """Test if `find_nth_occurrence` returns None when substring is not found."""
        test_values = (
            ("hello", "w", 1, None),
            ("hello", "w", 2, None),
            ("hello world", "world", 2, None),
            ("hello world", " ", 2, None),
            ("hello world", "o w", 2, None)
        )

        for string, substring, n, expected_index in test_values:
            with self.subTest(string=string, substring=substring, n=n):
                index = helpers.find_nth_occurrence(string, substring, n)
                self.assertEqual(index, expected_index)

    def test_has_lines_handles_normal_cases(self):
        """Test if `has_lines` returns True for strings with at least `count` lines."""
        test_values = (
            ("hello\nworld", 1, True),
            ("hello\nworld", 2, True),
            ("hello\nworld", 3, False),
        )

        for string, count, expected in test_values:
            with self.subTest(string=string, count=count):
                result = helpers.has_lines(string, count)
                self.assertEqual(result, expected)

    def test_has_lines_handles_empty_string(self):
        """Test if `has_lines` returns False for empty strings."""
        test_values = (
            ("", 0, False),
            ("", 1, False),
        )

        for string, count, expected in test_values:
            with self.subTest(string=string, count=count):
                result = helpers.has_lines(string, count)
                self.assertEqual(result, expected)

    def test_has_lines_handles_newline_at_end(self):
        """Test if `has_lines` ignores one newline at the end."""
        test_values = (
            ("hello\nworld\n", 2, True),
            ("hello\nworld\n", 3, False),
            ("hello\nworld\n\n", 3, True),
        )

        for string, count, expected in test_values:
            with self.subTest(string=string, count=count):
                result = helpers.has_lines(string, count)
                self.assertEqual(result, expected)

    def test_pad_base64_correctly(self):
        """Test if `pad_base64` correctly pads a base64 string."""
        test_values = (
            ("", ""),
            ("a", "a==="),
            ("aa", "aa=="),
            ("aaa", "aaa="),
            ("aaaa", "aaaa"),
            ("aaaaa", "aaaaa==="),
            ("aaaaaa", "aaaaaa=="),
            ("aaaaaaa", "aaaaaaa=")
        )

        for data, expected in test_values:
            with self.subTest(data=data):
                result = helpers.pad_base64(data)
                self.assertEqual(result, expected)

    def test_remove_subdomain_from_url_correctly(self):
        """Test if `remove_subdomain_from_url` correctly removes subdomains from URLs."""
        test_values = (
            ("https://example.com", "https://example.com"),
            ("https://www.example.com", "https://example.com"),
            ("https://sub.example.com", "https://example.com"),
            ("https://sub.sub.example.com", "https://example.com"),
            ("https://sub.example.co.uk", "https://example.co.uk"),
            ("https://sub.sub.example.co.uk", "https://example.co.uk"),
            ("https://sub.example.co.uk/path", "https://example.co.uk/path"),
            ("https://sub.sub.example.co.uk/path", "https://example.co.uk/path"),
            ("https://sub.example.co.uk/path?query", "https://example.co.uk/path?query"),
            ("https://sub.sub.example.co.uk/path?query", "https://example.co.uk/path?query"),
        )

        for url, expected in test_values:
            with self.subTest(url=url):
                result = helpers.remove_subdomain_from_url(url)
                self.assertEqual(result, expected)
