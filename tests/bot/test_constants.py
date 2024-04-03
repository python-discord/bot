import os
from pathlib import Path
from unittest import TestCase, mock

from pydantic import BaseModel

from bot.constants import EnvConfig

current_path = Path(__file__)
env_file_path = current_path.parent / ".testenv"


class _TestEnvConfig(
    EnvConfig,
    env_file=env_file_path,
):
    """Our default configuration for models that should load from .env files."""


class NestedModel(BaseModel):
    server_name: str


class _TestConfig(_TestEnvConfig, env_prefix="unittests_"):

    goat: str
    execution_env: str = "local"
    nested: NestedModel


class ConstantsTests(TestCase):
    """Tests for our constants."""

    @mock.patch.dict(os.environ, {"UNITTESTS_EXECUTION_ENV": "production"})
    def test_section_configuration_matches_type_specification(self):
        """"The section annotations should match the actual types of the sections."""

        testconfig = _TestConfig()
        self.assertEqual("volcyy", testconfig.goat)
        self.assertEqual("pydis", testconfig.nested.server_name)
        self.assertEqual("production", testconfig.execution_env)
