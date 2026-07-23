import asyncio
import contextlib
import importlib
import sys
import unittest
import unittest.mock
from pathlib import Path
from tempfile import TemporaryDirectory

import discord

from bot.bot import Bot


class ExtensionLoadingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.http_session = unittest.mock.MagicMock(name="http_session")

        # Set up a Bot instance with minimal configuration for testing extension loading.
        self.bot = Bot(
            command_prefix="!",
            guild_id=123456789012345678,
            allowed_roles=[],
            http_session=self.http_session,
            intents=discord.Intents.none()
        )

        # Avoid blocking in _load_extensions()
        async def _instant() -> None:
            return None
        self.bot.wait_until_guild_available = _instant

        # Ensure clean state
        self.bot.extension_load_failures = {}
        self.bot._extension_load_tasks = {}

        # Temporary importable package: tmp_root/testexts/__init__.py + modules
        self._temp_dir = TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.tmp_root = Path(self._temp_dir.name)

        self.pkg_name = "testexts"
        self.pkg_dir = self.tmp_root / self.pkg_name
        self.pkg_dir.mkdir(parents=True, exist_ok=True)
        (self.pkg_dir / "__init__.py").write_text("", encoding="utf-8")

        sys.path.insert(0, str(self.tmp_root))
        self.addCleanup(self._remove_tmp_from_syspath)
        self._purge_modules(self.pkg_name)

        # Ensure scheduled tasks execute during tests
        self._create_task_patcher = unittest.mock.patch(
            "pydis_core.utils.scheduling.create_task",
            side_effect=lambda coro, *a, **k: asyncio.create_task(coro),
        )
        self._create_task_patcher.start()
        self.addCleanup(self._create_task_patcher.stop)

    def _remove_tmp_from_syspath(self) -> None:
        """Remove the temporary directory from sys.path."""
        with contextlib.suppress(ValueError):
            sys.path.remove(str(self.tmp_root))

    def _purge_modules(self, prefix: str) -> None:
        """Remove modules from sys.modules that match the given prefix."""
        for name in list(sys.modules.keys()):
            if name == prefix or name.startswith(prefix + "."):
                del sys.modules[name]

    def _write_ext(self, module_name: str, source: str) -> str:
        """Write an extension module with the given source code and
        return its full import path."""
        (self.pkg_dir / f"{module_name}.py").write_text(source, encoding="utf-8")
        full = f"{self.pkg_name}.{module_name}"
        self._purge_modules(full)
        return full

    async def _run_loader(self) -> None:
        """Run the extension loader on the package containing our test extensions."""
        module = importlib.import_module(self.pkg_name)

        await self.bot._load_extensions(module)

        # Wait for all extension load tasks to complete so that exceptions are recorded in the bot's state
        tasks = getattr(self.bot, "_extension_load_tasks", {}) or {}
        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    def _assert_failure_recorded_for_extension(self, ext: str) -> None:
        """Assert that a failure is recorded for the given extension."""
        if ext in self.bot.extension_load_failures:
            return
        for key in self.bot.extension_load_failures:
            if key.startswith(ext):
                return
        self.fail(
            f"Expected a failure recorded for {ext!r}. "
            f"Recorded keys: {sorted(self.bot.extension_load_failures.keys())}"
        )

    async def test_setup_failure_is_captured(self) -> None:
        ext = self._write_ext(
            "ext_setup_fail",
            """
async def setup(bot):
    raise RuntimeError("setup failed")
""",
        )
        await self._run_loader()
        self._assert_failure_recorded_for_extension(ext)

    async def test_cog_load_failure_is_captured(self) -> None:
        ext = self._write_ext(
            "ext_cogload_fail",
            """
from discord.ext import commands

class BadCog(commands.Cog):
    async def cog_load(self):
        raise RuntimeError("cog_load failed")

async def setup(bot):
    await bot.add_cog(BadCog())
""",
        )
        await self._run_loader()
        self._assert_failure_recorded_for_extension(ext)

    async def test_add_cog_failure_is_captured(self) -> None:
        ext = self._write_ext(
            "ext_addcog_fail",
            """
from discord.ext import commands

class DupCog(commands.Cog):
    pass

async def setup(bot):
    await bot.add_cog(DupCog())
    await bot.add_cog(DupCog())
""",
        )
        await self._run_loader()
        self._assert_failure_recorded_for_extension(ext)

    async def test_import_failure_is_captured(self) -> None:
        ext = self._write_ext(
            "ext_import_fail",
            """
raise RuntimeError("import failed before setup()")

async def setup(bot):
    pass
""",
        )
        await self._run_loader()
        self._assert_failure_recorded_for_extension(ext)
