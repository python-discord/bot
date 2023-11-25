"""This module provides functions for parsing Markdown code blocks."""

import ast
import re
import textwrap
from collections.abc import Sequence
from typing import NamedTuple

from bot import constants
from bot.log import get_logger
from bot.utils import has_lines

log = get_logger(__name__)

BACKTICK = "`"
PY_LANG_CODES = ("python-repl", "python", "pycon", "py")  # Order is important; "py" is last cause it's a subset.
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

_RE_PYTHON_REPL = re.compile(r"^(>>>|\.\.\.)( |$)")
_RE_IPYTHON_REPL = re.compile(r"^((In|Out) \[\d+\]: |\s*\.{3,}: ?)")

_RE_CODE_BLOCK = re.compile(
    fr"""
    (?P<ticks>
        (?P<tick>[{''.join(_TICKS)}]) # Put all ticks into a character class within a group.
        \2{{2}}                       # Match previous group 2 more times to ensure the same char.
    )
    (?P<lang>[A-Za-z0-9\+\-\.]+\n)?   # Optionally match a language specifier followed by a newline.
    (?P<code>.+?)                     # Match the actual code within the block.
    \1                                # Match the same 3 ticks used at the start of the block.
    """,
    re.DOTALL | re.VERBOSE
)

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
    has_leading_spaces: bool
    has_terminal_newline: bool


def find_code_blocks(message: str) -> Sequence[CodeBlock] | None:
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
        if has_lines(groups["code"], constants.CodeBlock.minimum_lines):
            code_block = CodeBlock(groups["code"], language, groups["tick"])
            code_blocks.append(code_block)
        else:
            log.trace("Skipped a code block shorter than 4 lines.")

    return code_blocks


def _is_python_code(content: str) -> bool:
    """Return True if `content` is valid Python consisting of more than just expressions."""
    log.trace("Checking if content is Python code.")
    try:
        # Remove null bytes because they cause ast.parse to raise a ValueError.
        content = content.replace("\x00", "")

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

    log.trace("Code consists only of expressions.")
    return False


def _is_repl_code(content: str, threshold: int = 3) -> bool:
    """Return True if `content` has at least `threshold` number of (I)Python REPL-like lines."""
    log.trace(f"Checking if content is (I)Python REPL code using a threshold of {threshold}.")

    repl_lines = 0
    patterns = (_RE_PYTHON_REPL, _RE_IPYTHON_REPL)

    for line in content.splitlines():
        # Check the line against all patterns.
        for pattern in patterns:
            if pattern.match(line):
                repl_lines += 1

                # Once a pattern is matched, only use that pattern for the remaining lines.
                patterns = (pattern,)
                break

        if repl_lines == threshold:
            log.trace("Content is (I)Python REPL code.")
            return True

    log.trace("Content is not (I)Python REPL code.")
    return False


def is_python_code(content: str) -> bool:
    """Return True if `content` is valid Python code or (I)Python REPL output."""
    dedented = textwrap.dedent(content)

    # Parse AST twice in case _fix_indentation ends up breaking code due to its inaccuracies.
    return (
        _is_python_code(dedented)
        or _is_repl_code(dedented)
        or _is_python_code(_fix_indentation(content))
    )


def parse_bad_language(content: str) -> BadLanguage | None:
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
        has_leading_spaces=match["spaces"] is not None,
        has_terminal_newline=match["newline"] is not None,
    )


def _get_leading_spaces(content: str) -> int:
    """Return the number of spaces at the start of the first line in `content`."""
    leading_spaces = 0
    for char in content:
        if char == " ":
            leading_spaces += 1
        else:
            return leading_spaces
    return None


def _fix_indentation(content: str) -> str:
    """
    Attempt to fix badly indented code in `content`.

    In most cases, this works like textwrap.dedent. However, if the first line ends with a colon,
    all subsequent lines are re-indented to only be one level deep relative to the first line.
    The intent is to fix cases where the leading spaces of the first line of code were accidentally
    not copied, which makes the first line appear not indented.

    This is fairly naïve and inaccurate. Therefore, it may break some code that was otherwise valid.
    It's meant to catch really common cases, so that's acceptable. Its flaws are:

    - It assumes that if the first line ends with a colon, it is the start of an indented block
    - It uses 4 spaces as the indentation, regardless of what the rest of the code uses
    """
    lines = content.splitlines(keepends=True)

    # Dedent the first line
    first_indent = _get_leading_spaces(content)
    first_line = lines[0][first_indent:]

    # Can't assume there'll be multiple lines cause line counts of edited messages aren't checked.
    if len(lines) == 1:
        return first_line

    second_indent = _get_leading_spaces(lines[1])

    # If the first line ends with a colon, all successive lines need to be indented one
    # additional level (assumes an indent width of 4).
    if first_line.rstrip().endswith(":"):
        second_indent -= 4

    # All lines must be dedented at least by the same amount as the first line.
    first_indent = max(first_indent, second_indent)

    # Dedent the rest of the lines and join them together with the first line.
    content = first_line + "".join(line[first_indent:] for line in lines[1:])

    return content
