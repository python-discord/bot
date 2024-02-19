import os
import unittest
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings

current_path = Path(__file__)
env_file_path = current_path.parent / ".testenv"

ci_context = int(os.environ.get("UNITTESTS_CI_CONTEXT", 0))


class TestEnvConfig(
    BaseSettings,
    env_file=env_file_path,
    env_file_encoding="utf-8",
    env_nested_delimiter="__",
    extra="ignore",
):
    """Our default configuration for models that should load from .env files."""


class NestedModel(BaseModel):
    server_name: str


class _TestConfig(TestEnvConfig, env_prefix="unittests_"):

    goat: str
    execution_env: str = "local"
    nested: NestedModel


class ConstantsTests(unittest.TestCase):
    """Tests for our constants."""

    def test_section_configuration_matches_type_specification(self):
        """"The section annotations should match the actual types of the sections."""

        testconfig = _TestConfig()
        self.assertEqual("volcyy", testconfig.goat)
        self.assertEqual("pydis", testconfig.nested.server_name)
        expected_execution_env = "CI" if ci_context else "local"
        self.assertEqual(expected_execution_env, testconfig.execution_env)
