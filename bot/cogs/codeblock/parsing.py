import ast
import logging
import re
from typing import NamedTuple, Sequence

import discord

log = logging.getLogger(__name__)

RE_MARKDOWN = re.compile(r'([*_~`|>])')
RE_CODE_BLOCK_LANGUAGE = re.compile(r"```(?:[^\W_]+)\n(.*?)```", re.DOTALL)
BACKTICK = "`"
TICKS = {
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
RE_CODE_BLOCK = re.compile(
    fr"""
    (
        ([{''.join(TICKS)}])  # Put all ticks into a character class within a group.
        \2{{2}}               # Match the previous group 2 more times to ensure it's the same char.
    )
    ([^\W_]+\n)?              # Optionally match a language specifier followed by a newline.
    (.+?)                     # Match the actual code within the block.
    \1                        # Match the same 3 ticks used at the start of the block.
    """,
    re.DOTALL | re.VERBOSE
)


class CodeBlock(NamedTuple):
    """Represents a Markdown code block."""

    content: str
    language: str
    tick: str


def find_code_blocks(message: str) -> Sequence[CodeBlock]:
    """
    Find and return all Markdown code blocks in the `message`.

    Code blocks with 3 or less lines are excluded.

    If the `message` contains at least one code block with valid ticks and a specified language,
    return an empty sequence. This is based on the assumption that if the user managed to get
    one code block right, they already know how to fix the rest themselves.
    """
    code_blocks = []
    for _, tick, language, content in RE_CODE_BLOCK.finditer(message):
        language = language.strip()
        if tick == BACKTICK and language:
            return ()
        elif len(content.split("\n", 3)) > 3:
            code_block = CodeBlock(content, language, tick)
            code_blocks.append(code_block)


def has_bad_ticks(message: discord.Message) -> bool:
    """Return True if `message` starts with 3 characters which look like but aren't '`'."""
    return message.content[:3] in TICKS


def is_python_code(content: str) -> bool:
    """Return True if `content` is valid Python consisting of more than just expressions."""
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
        return True
    else:
        log.trace("Code consists only of expressions.")
        return False


def is_repl_code(content: str, threshold: int = 3) -> bool:
    """Return True if `content` has at least `threshold` number of Python REPL-like lines."""
    repl_lines = 0
    for line in content.splitlines():
        if line.startswith(">>> ") or line.startswith("... "):
            repl_lines += 1

        if repl_lines == threshold:
            return True

    return False


def truncate(content: str, max_chars: int = 204, max_lines: int = 10) -> str:
    """Return `content` truncated to be at most `max_chars` or `max_lines` in length."""
    current_length = 0
    lines_walked = 0

    for line in content.splitlines(keepends=True):
        if current_length + len(line) > max_chars or lines_walked == max_lines:
            break
        current_length += len(line)
        lines_walked += 1

    return content[:current_length] + "#..."
