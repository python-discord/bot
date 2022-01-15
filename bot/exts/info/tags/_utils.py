from __future__ import annotations

import enum
import re
import time
from pathlib import Path
from typing import NamedTuple, Optional

import discord
import frontmatter
from discord import Embed

from bot import constants
from bot.log import get_logger

log = get_logger(__name__)

__all__ = (
    "REGEX_NON_ALPHABET",
    "COOLDOWN",
    "TagIdentifier",
    "Tag",
)
REGEX_NON_ALPHABET = re.compile(r"[^a-z]", re.MULTILINE & re.IGNORECASE)


class COOLDOWN(enum.Enum):
    """Sentinel value to signal that a tag is on cooldown."""

    obj = object()


class TagIdentifier(NamedTuple):
    """Stores the group and name used as an identifier for a tag."""

    group: Optional[str]
    name: str

    def get_fuzzy_score(self, fuzz_tag_identifier: TagIdentifier) -> float:
        """Get fuzzy score, using `fuzz_tag_identifier` as the identifier to fuzzy match with."""
        if (self.group is None) != (fuzz_tag_identifier.group is None):
            # Ignore tags without groups if the identifier has a group and vice versa
            return 0.0
        if self.group == fuzz_tag_identifier.group:
            # Completely identical, or both None
            group_score = 1
        else:
            group_score = _fuzzy_search(fuzz_tag_identifier.group, self.group)

        fuzzy_score = (
            group_score * _fuzzy_search(fuzz_tag_identifier.name, self.name) * 100
        )
        if fuzzy_score:
            log.trace(
                f"Fuzzy score {fuzzy_score:=06.2f} for tag {self!r} with fuzz {fuzz_tag_identifier!r}"
            )
        return fuzzy_score

    def __str__(self) -> str:
        if self.group is not None:
            return f"{self.group} {self.name}"
        else:
            return self.name

    @classmethod
    def from_string(cls, string: str) -> TagIdentifier:
        """Create a `TagIdentifier` instance from the beginning of `string`."""
        split_string = string.removeprefix(constants.Bot.prefix).split(" ", maxsplit=2)
        if len(split_string) == 1:
            return cls(None, split_string[0])
        else:
            return cls(split_string[0], split_string[1])


class Tag:
    """Provide an interface to a tag from resources with `file_content`."""

    def __init__(self, content_path: Path):
        post = frontmatter.loads(content_path.read_text("utf8"))
        self.file_path = content_path
        self.content = post.content
        self.metadata = post.metadata
        self._restricted_to: set[int] = set(self.metadata.get("restricted_to", ()))
        self._cooldowns: dict[discord.TextChannel, float] = {}

    @property
    def embed(self) -> Embed:
        """Create an embed for the tag."""
        embed = Embed.from_dict(self.metadata.get("embed", {}))
        embed.description = self.content
        return embed

    def accessible_by(self, member: discord.Member) -> bool:
        """Check whether `member` can access the tag."""
        return bool(
            not self._restricted_to
            or self._restricted_to & {role.id for role in member.roles}
        )

    def on_cooldown_in(self, channel: discord.TextChannel) -> bool:
        """Check whether the tag is on cooldown in `channel`."""
        return self._cooldowns.get(channel, float("-inf")) > time.time()

    def set_cooldown_for(self, channel: discord.TextChannel) -> None:
        """Set the tag to be on cooldown in `channel` for `constants.Cooldowns.tags` seconds."""
        self._cooldowns[channel] = time.time() + constants.Cooldowns.tags


def _fuzzy_search(search: str, target: str) -> float:
    """A simple scoring algorithm based on how many letters are found / total, with order in mind."""
    _search = REGEX_NON_ALPHABET.sub("", search.lower())
    if not _search:
        return 0

    _targets = iter(REGEX_NON_ALPHABET.split(target.lower()))

    current = 0
    for _target in _targets:
        index = 0
        try:
            while index < len(_target) and _search[current] == _target[index]:
                current += 1
                index += 1
        except IndexError:
            # Exit when _search runs out
            break

    return current / len(_search)
