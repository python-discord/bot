from abc import ABCMeta
from urllib.parse import urlparse

from discord.ext.commands import CogMeta
from tldextract import extract


class CogABCMeta(CogMeta, ABCMeta):
    """Metaclass for ABCs meant to be implemented as Cogs."""


def find_nth_occurrence(string: str, substring: str, n: int) -> int | None:
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


def remove_subdomain_from_url(url: str) -> str:
    """Removes subdomains from a URL whilst preserving the original URL composition."""
    parsed_url = urlparse(url)
    extracted_url = extract(url)
    # Eliminate subdomain by using the registered domain only
    netloc = extracted_url.registered_domain
    parsed_url = parsed_url._replace(netloc=netloc)
    return parsed_url.geturl()
