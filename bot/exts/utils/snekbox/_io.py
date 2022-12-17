"""I/O File protocols for snekbox."""
from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from discord import File

# Note discord bot upload limit is 8 MiB per file,
# or 50 MiB for lvl 2 boosted servers
FILE_SIZE_LIMIT = 8 * 1024 * 1024

# Discord currently has a 10-file limit per message
FILE_COUNT_LIMIT = 10


def sizeof_fmt(num: int | float, suffix: str = "B") -> str:
    """Return a human-readable file size."""
    num = float(num)
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024:
            num_str = f"{int(num)}" if num.is_integer() else f"{num:3.1f}"
            return f"{num_str} {unit}{suffix}"
        num /= 1024
    num_str = f"{int(num)}" if num.is_integer() else f"{num:3.1f}"
    return f"{num_str} Yi{suffix}"


@dataclass
class FileAttachment:
    """File Attachment from Snekbox eval."""

    path: str
    content: bytes

    def __repr__(self) -> str:
        """Return the content as a string."""
        content = f"{self.content[:10]}..." if len(self.content) > 10 else self.content
        return f"FileAttachment(path={self.path!r}, content={content})"

    @classmethod
    def from_dict(cls, data: dict, size_limit: int = FILE_SIZE_LIMIT) -> FileAttachment:
        """Create a FileAttachment from a dict response."""
        size = data.get("size")
        if (size and size > size_limit) or (len(data["content"]) > size_limit):
            raise ValueError("File size exceeds limit")

        content = b64decode(data["content"])

        if len(content) > size_limit:
            raise ValueError("File size exceeds limit")

        return cls(data["path"], content)

    def to_dict(self) -> dict[str, str]:
        """Convert the attachment to a json dict."""
        content = self.content
        if isinstance(content, str):
            content = content.encode("utf-8")

        return {
            "path": self.path,
            "content": b64encode(content).decode("ascii"),
        }

    def to_file(self) -> File:
        """Convert to a discord.File."""
        name = Path(self.path).name
        return File(BytesIO(self.content), filename=name)
