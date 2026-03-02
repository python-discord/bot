import unittest
from unittest.mock import MagicMock

from pydis_core.site_api import ResponseCodeError

from bot.utils.retry import is_retryable_api_error


class RetryTests(unittest.TestCase):
    """Tests for retry classification helpers."""

    def test_is_retryable_api_error(self):
        """`is_retryable_api_error` should classify temporary failures as retryable."""
        test_cases = (
            (ResponseCodeError(MagicMock(status=408)), True),
            (ResponseCodeError(MagicMock(status=429)), True),
            (ResponseCodeError(MagicMock(status=500)), True),
            (ResponseCodeError(MagicMock(status=503)), True),
            (ResponseCodeError(MagicMock(status=400)), False),
            (ResponseCodeError(MagicMock(status=404)), False),
            (TimeoutError("timeout"), True),
            (OSError("os error"), True),
            (AttributeError("attr"), False),
            (ValueError("value"), False),
        )

        for error, expected_retryable in test_cases:
            with self.subTest(error=error):
                self.assertEqual(is_retryable_api_error(error), expected_retryable)
