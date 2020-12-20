import unittest
from unittest.mock import MagicMock

from bot import api


class APIClientTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the bot's API client."""

    @classmethod
    def setUpClass(cls):
        """Sets up the shared fixtures for the tests."""
        cls.error_api_response = MagicMock()
        cls.error_api_response.status = 999

    def test_response_code_error_default_initialization(self):
        """Test the default initialization of `ResponseCodeError` without `text` or `json`"""
        error = api.ResponseCodeError(response=self.error_api_response)

        self.assertIs(error.status, self.error_api_response.status)
        self.assertEqual(error.response_json, {})
        self.assertEqual(error.response_text, "")
        self.assertIs(error.response, self.error_api_response)

    def test_response_code_error_string_representation_default_initialization(self):
        """Test the string representation of `ResponseCodeError` initialized without text or json."""
        error = api.ResponseCodeError(response=self.error_api_response)
        self.assertEqual(str(error), f"Status: {self.error_api_response.status} Response: ")

    def test_response_code_error_initialization_with_json(self):
        """Test the initialization of `ResponseCodeError` with json."""
        json_data = {'hello': 'world'}
        error = api.ResponseCodeError(
            response=self.error_api_response,
            response_json=json_data,
        )
        self.assertEqual(error.response_json, json_data)
        self.assertEqual(error.response_text, "")

    def test_response_code_error_string_representation_with_nonempty_response_json(self):
        """Test the string representation of `ResponseCodeError` initialized with json."""
        json_data = {'hello': 'world'}
        error = api.ResponseCodeError(
            response=self.error_api_response,
            response_json=json_data
        )
        self.assertEqual(str(error), f"Status: {self.error_api_response.status} Response: {json_data}")

    def test_response_code_error_initialization_with_text(self):
        """Test the initialization of `ResponseCodeError` with text."""
        text_data = 'Lemon will eat your soul'
        error = api.ResponseCodeError(
            response=self.error_api_response,
            response_text=text_data,
        )
        self.assertEqual(error.response_text, text_data)
        self.assertEqual(error.response_json, {})

    def test_response_code_error_string_representation_with_nonempty_response_text(self):
        """Test the string representation of `ResponseCodeError` initialized with text."""
        text_data = 'Lemon will eat your soul'
        error = api.ResponseCodeError(
            response=self.error_api_response,
            response_text=text_data
        )
        self.assertEqual(str(error), f"Status: {self.error_api_response.status} Response: {text_data}")
