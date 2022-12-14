from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from signal import Signals
from typing import TYPE_CHECKING

from bot.exts.utils.snekbox._io import FILE_SIZE_LIMIT, FileAttachment, sizeof_fmt
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
    err_files: list[str] = field(default_factory=list)

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

    def get_message(self, job: EvalJob) -> tuple[str, str]:
        """Return a user-friendly message and error corresponding to the process's return code."""
        msg = f"Your {job.version} {job.name} job has completed with return code {self.returncode}"
        error = ""

        if self.returncode is None:
            msg = f"Your {job.version} {job.name} job has failed"
            error = self.stdout.strip()
        elif self.returncode == 128 + SIGKILL:
            msg = f"Your {job.version} {job.name} job timed out or ran out of memory"
        elif self.returncode == 255:
            msg = f"Your {job.version} {job.name} job has failed"
            error = "A fatal NsJail error occurred"
        else:
            # Try to append signal's name if one exists
            with contextlib.suppress(ValueError):
                name = Signals(self.returncode - 128).name
                msg = f"{msg} ({name})"

        # Add error message for failed attachments
        if self.err_files:
            failed_files = f"({', '.join(self.err_files)})"
            msg += (
                f".\n\n> Some attached files were not able to be uploaded {failed_files}."
                f" Check that the file size is less than {sizeof_fmt(FILE_SIZE_LIMIT)}"
            )

        return msg, error

    @classmethod
    def from_dict(cls, data: dict[str, str | int | list[dict[str, str]]]) -> EvalResult:
        """Create an EvalResult from a dict."""
        res = cls(
            stdout=data["stdout"],
            returncode=data["returncode"],
        )

        for file in data.get("files", []):
            try:
                res.files.append(FileAttachment.from_dict(file))
            except ValueError as e:
                log.info(f"Failed to parse file from snekbox response: {e}")
                res.err_files.append(file["path"])

        return res
