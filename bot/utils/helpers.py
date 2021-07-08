from abc import ABCMeta
from typing import Dict, List, Optional

from discord import Guild
from discord.ext.commands import CogMeta


class CogABCMeta(CogMeta, ABCMeta):
    """Metaclass for ABCs meant to be implemented as Cogs."""


def find_nth_occurrence(string: str, substring: str, n: int) -> Optional[int]:
    """Return index of `n`th occurrence of `substring` in `string`, or None if not found."""
    index = 0
    for _ in range(n):
        index = string.find(substring, index+1)
        if index == -1:
            return None
    return index


def has_lines(string: str, count: int) -> bool:
    """Return True if `string` has at least `count` lines."""
    # Benchmarks show this is significantly faster than using str.count("\n") or a for loop & break.
    split = string.split("\n", count - 1)

    # Make sure the last part isn't empty, which would happen if there was a final newline.
    return split[-1] and len(split) == count


def pad_base64(data: str) -> str:
    """Return base64 `data` with padding characters to ensure its length is a multiple of 4."""
    return data + "=" * (-len(data) % 4)


def join_role_stats(role_ids: List[int], name: str, guild: Guild) -> Dict[str, int]:
    """Return a dict object with the number of `members` of each role given, and the `name` for this joined group."""
    members = []
    for role_id in role_ids:
        members += guild.get_role(role_id).members
    return {name: len(set(members))}
