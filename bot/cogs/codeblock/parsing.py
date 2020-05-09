"""This module provides functions for parsing Markdown code blocks."""

import ast
import logging
import re
from typing import NamedTuple, Optional, Sequence

from bot.utils import has_lines

log = logging.getLogger(__name__)

BACKTICK = "`"
_TICKS = {
    BACKTICK,
    "'",
    '"',
    "\u00b4",  # ACUTE ACCENT
    "\u2018",  # LEFT SINGLE QUOTATION MARK
    "\u2019",  # RIGHT SINGLE QUOTATION MARK
    "\u2032",  # PRIME
    "\u201c",  # LEFT DOUBLE QUOTATION MARK
    "\u201d",  # RIGHT DOUBLE QUOTATION MARK
    "\u2033",  # DOUBLE PRIME
    "\u3003",  # VERTICAL KANA REPEAT MARK UPPER HALF
}
_RE_CODE_BLOCK = re.compile(
    fr"""
    (?P<ticks>
        (?P<tick>[{''.join(_TICKS)}]) # Put all ticks into a character class within a group.
        \2{{2}}                       # Match previous group 2 more times to ensure the same char.
    )
    (?P<lang>[^\W_]+\n)?              # Optionally match a language specifier followed by a newline.
    (?P<code>.+?)                     # Match the actual code within the block.
    \1                                # Match the same 3 ticks used at the start of the block.
    """,
    re.DOTALL | re.VERBOSE
)

PY_LANG_CODES = ("python", "py")  # Order is important; "py" is second cause it's a subset.
_RE_LANGUAGE = re.compile(
    fr"""
    ^(?P<spaces>\s+)?                    # Optionally match leading spaces from the beginning.
    (?P<lang>{'|'.join(PY_LANG_CODES)})  # Match a Python language.
    (?P<newline>\n)?                     # Optionally match a newline following the language.
    """,
    re.IGNORECASE | re.VERBOSE
)


class CodeBlock(NamedTuple):
    """Represents a Markdown code block."""

    content: str
    language: str
    tick: str


class BadLanguage(NamedTuple):
    """Parsed information about a poorly formatted language specifier."""

    language: str
    leading_spaces: bool
    terminal_newline: bool


def find_code_blocks(message: str) -> Optional[Sequence[CodeBlock]]:
    """
    Find and return all Markdown code blocks in the `message`.

    Code blocks with 3 or fewer lines are excluded.

    If the `message` contains at least one code block with valid ticks and a specified language,
    return None. This is based on the assumption that if the user managed to get one code block
    right, they already know how to fix the rest themselves.
    """
    log.trace("Finding all code blocks in a message.")

    code_blocks = []
    for match in _RE_CODE_BLOCK.finditer(message):
        # Used to ensure non-matched groups have an empty string as the default value.
        groups = match.groupdict("")
        language = groups["lang"].strip()  # Strip the newline cause it's included in the group.

        if groups["tick"] == BACKTICK and language:
            log.trace("Message has a valid code block with a language; returning None.")
            return None
        elif has_lines(groups["code"], 4):
            code_block = CodeBlock(groups["code"], language, groups["tick"])
            code_blocks.append(code_block)
        else:
            log.trace("Skipped a code block shorter than 4 lines.")

    return code_blocks


def is_python_code(content: str) -> bool:
    """Return True if `content` is valid Python consisting of more than just expressions."""
    log.trace("Checking if content is Python code.")
    try:
        # Attempt to parse the message into an AST node.
        # Invalid Python code will raise a SyntaxError.
        tree = ast.parse(content)
    except SyntaxError:
        log.trace("Code is not valid Python.")
        return False

    # Multiple lines of single words could be interpreted as expressions.
    # This check is to avoid all nodes being parsed as expressions.
    # (e.g. words over multiple lines)
    if not all(isinstance(node, ast.Expr) for node in tree.body):
        log.trace("Code is valid python.")
        return True
    else:
        log.trace("Code consists only of expressions.")
        return False


def is_repl_code(content: str, threshold: int = 3) -> bool:
    """Return True if `content` has at least `threshold` number of Python REPL-like lines."""
    log.trace(f"Checking if content is Python REPL code using a threshold of {threshold}.")

    repl_lines = 0
    for line in content.splitlines():
        if line.startswith(">>> ") or line.startswith("... "):
            repl_lines += 1

        if repl_lines == threshold:
            log.trace("Content is Python REPL code.")
            return True

    log.trace("Content is not Python REPL code.")
    return False


def parse_bad_language(content: str) -> Optional[BadLanguage]:
    """
    Return information about a poorly formatted Python language in code block `content`.

    If the language is not Python, return None.
    """
    log.trace("Parsing bad language.")

    match = _RE_LANGUAGE.match(content)
    if not match:
        return None

    return BadLanguage(
        language=match["lang"],
        leading_spaces=match["spaces"] is not None,
        terminal_newline=match["newline"] is not None,
    )
