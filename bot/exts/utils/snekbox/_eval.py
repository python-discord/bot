from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from signal import Signals
from typing import TYPE_CHECKING

from bot.exts.utils.snekbox._io import FILE_COUNT_LIMIT, FILE_SIZE_LIMIT, FileAttachment, sizeof_fmt
from bot.log import get_logger

if TYPE_CHECKING:
    from bot.exts.utils.snekbox._cog import PythonVersion

log = get_logger(__name__)

SIGKILL = 9


@dataclass
class EvalJob:
    """Job to be evaluated by snekbox."""

    args: list[str]
    files: list[FileAttachment] = field(default_factory=list)
    name: str = "eval"
    version: PythonVersion = "3.11"

    @classmethod
    def from_code(cls, code: str, path: str = "main.py") -> EvalJob:
        """Create an EvalJob from a code string."""
        return cls(
            args=[path],
            files=[FileAttachment(path, code.encode())],
        )

    def as_version(self, version: PythonVersion) -> EvalJob:
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
    def status_emoji(self) -> str:
        """Return an emoji corresponding to the status code or lack of output in result."""
        # If there are attachments, skip empty output warning
        if not self.stdout.strip() and not self.files:  # No output
            return ":warning:"
        elif self.returncode == 0:  # No error
            return ":white_check_mark:"
        else:  # Exception
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

        failed_files = f"({self.failed_files_str()})"

        n_failed = len(self.failed_files)
        files = f"file{'s' if n_failed > 1 else ''}"
        msg = f"Failed to upload {n_failed} {files} {failed_files}"

        if (n_failed + len(self.files)) > FILE_COUNT_LIMIT:
            it_they = "they" if n_failed > 1 else "it"
            msg += f" as {it_they} exceeded the {FILE_COUNT_LIMIT} file limit."
        else:
            msg += f". File sizes should each not exceed {sizeof_fmt(FILE_SIZE_LIMIT)}."

        return msg

    def failed_files_str(self, char_max: int = 85, file_max: int = 5) -> str:
        """Return a string containing the names of failed files, truncated to lower of char_max and file_max."""
        names = []
        for file in self.failed_files:
            char_max -= len(file)
            if char_max <= 0 or len(names) >= file_max:
                names.append("...")
                break
            names.append(file)
        text = ", ".join(names)
        return text

    def get_message(self, job: EvalJob) -> str:
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
