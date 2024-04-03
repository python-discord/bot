from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from signal import Signals
from typing import TYPE_CHECKING

from discord.utils import escape_markdown, escape_mentions

from bot.constants import Emojis
from bot.exts.utils.snekbox._io import FILE_COUNT_LIMIT, FILE_SIZE_LIMIT, FileAttachment, sizeof_fmt
from bot.log import get_logger

if TYPE_CHECKING:
    from bot.exts.utils.snekbox._cog import SupportedPythonVersions

log = get_logger(__name__)

SIGKILL = 9


@dataclass(frozen=True)
class EvalJob:
    """Job to be evaluated by snekbox."""

    args: list[str]
    files: list[FileAttachment] = field(default_factory=list)
    name: str = "eval"
    version: SupportedPythonVersions = "3.12"

    @classmethod
    def from_code(cls, code: str, path: str = "main.py") -> EvalJob:
        """Create an EvalJob from a code string."""
        return cls(
            args=[path],
            files=[FileAttachment(path, code.encode())],
        )

    def as_version(self, version: SupportedPythonVersions) -> EvalJob:
        """Return a copy of the job with a different Python version."""
        return EvalJob(
            args=self.args,
            files=self.files,
            name=self.name,
            version=version,
        )

    def to_dict(self) -> dict[str, list[str | dict[str, str]]]:
        """Convert the job to a dict."""
        return {
            "args": self.args,
            "files": [file.to_dict() for file in self.files],
        }


@dataclass(frozen=True)
class EvalResult:
    """The result of an eval job."""

    stdout: str
    returncode: int | None
    files: list[FileAttachment] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)

    @property
    def has_output(self) -> bool:
        """True if the result has any output (stdout, files, or failed files)."""
        return bool(self.stdout.strip() or self.files or self.failed_files)

    @property
    def has_files(self) -> bool:
        """True if the result has any files or failed files."""
        return bool(self.files or self.failed_files)

    @property
    def status_emoji(self) -> str:
        """Return an emoji corresponding to the status code or lack of output in result."""
        if not self.has_output:
            return ":warning:"
        if self.returncode == 0:  # No error
            return ":white_check_mark:"
        # Exception
        return ":x:"

    @property
    def error_message(self) -> str:
        """Return an error message corresponding to the process's return code."""
        error = ""
        if self.returncode is None:
            error = self.stdout.strip()
        elif self.returncode == 255:
            error = "A fatal NsJail error occurred"
        return error

    @property
    def files_error_message(self) -> str:
        """Return an error message corresponding to the failed files."""
        if not self.failed_files:
            return ""

        failed_files = f"({self.get_failed_files_str()})"

        n_failed = len(self.failed_files)
        s_upload = "uploads" if n_failed > 1 else "upload"

        msg = f"{Emojis.failed_file} {n_failed} file {s_upload} {failed_files} failed"

        # Exceeded file count limit
        if (n_failed + len(self.files)) > FILE_COUNT_LIMIT:
            s_it = "they" if n_failed > 1 else "it"
            msg += f" as {s_it} exceeded the {FILE_COUNT_LIMIT} file limit."
        # Exceeded file size limit
        else:
            s_each_file = "each file's" if n_failed > 1 else "its file"
            msg += f" because {s_each_file} size exceeds {sizeof_fmt(FILE_SIZE_LIMIT)}."

        return msg

    def get_failed_files_str(self, char_max: int = 85) -> str:
        """
        Return a string containing the names of failed files, truncated char_max.

        Will truncate on whole file names if less than 3 characters remaining.
        """
        names = []
        for file in self.failed_files:
            # Only attempt to truncate name if more than 3 chars remaining
            if char_max < 3:
                names.append("...")
                break

            if len(file) > char_max:
                names.append(file[:char_max] + "...")
                break
            char_max -= len(file)
            names.append(file)

        text = ", ".join(names)
        # Since the file names are provided by user
        text = escape_markdown(text)
        text = escape_mentions(text)
        return text

    def get_status_message(self, job: EvalJob) -> str:
        """Return a user-friendly message corresponding to the process's return code."""
        msg = f"Your {job.version} {job.name} job"

        if self.returncode is None:
            msg += " has failed"
        elif self.returncode == 128 + SIGKILL:
            msg += " timed out or ran out of memory"
        elif self.returncode == 255:
            msg += " has failed"
        else:
            msg += f" has completed with return code {self.returncode}"
            # Try to append signal's name if one exists
            with contextlib.suppress(ValueError):
                name = Signals(self.returncode - 128).name
                msg += f" ({name})"

        return msg

    @classmethod
    def from_dict(cls, data: dict[str, str | int | list[dict[str, str]]]) -> EvalResult:
        """Create an EvalResult from a dict."""
        res = cls(
            stdout=data["stdout"],
            returncode=data["returncode"],
        )

        files = iter(data["files"])
        for i, file in enumerate(files):
            # Limit to FILE_COUNT_LIMIT files
            if i >= FILE_COUNT_LIMIT:
                res.failed_files.extend(file["path"] for file in files)
                break
            try:
                res.files.append(FileAttachment.from_dict(file))
            except ValueError as e:
                log.info(f"Failed to parse file from snekbox response: {e}")
                res.failed_files.append(file["path"])

        return res
