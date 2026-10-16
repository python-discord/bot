import itertools

import black

from bot import constants
from bot.exts.info.codeblock import _parsing
from bot.log import get_logger

log = get_logger(__name__)


def _code_as_markdown(code: str) -> str:
    return f"{_parsing.BACKTICK * 3}py\n{code}\n{_parsing.BACKTICK * 3}"


def _try_format_with_black(code: str) -> str | None:
    try:
        return black.format_str(code, mode=black.FileMode())
    except black.InvalidInput:
        log.debug("automatic formatting with Black failed")
        return None


def _attempt_formatting_whole_content(content: str) -> str | None:
    if _parsing.is_python_code(content):
        formatted_code = _try_format_with_black(content)
        if formatted_code is None:
            log.trace("Code is detected as Python code but Black formatting failed.")
            return None

        if not formatted_code:
            log.error(
                "Code has been detected as Python code, Black formatting didn't fail, but no output was produced. "
                "This should never happen.")
            return None

        return formatted_code
    return None


def _merge_non_code_blocks_with_code_blocks(non_code_blocks: list[str], formatted_code_blocks: list[str]) -> str:
    return "".join(
        f"{non_code_block}{formatted_code_block and _code_as_markdown(formatted_code_block)}"
        for non_code_block, formatted_code_block
        in itertools.zip_longest(non_code_blocks, formatted_code_blocks, fillvalue="")
    )


def try_fix_markdown(content: str) -> str | None:
    """
    Converts the user's content to a properly formatted Markdown message if it finds a non-formatted code block.

    Returns None if it encounters any problems.
    """
    log.trace("Try to automatically format code blocks.")
    formatted_content = _attempt_formatting_whole_content(content)
    if formatted_content is not None:
        return _code_as_markdown(formatted_content)

    code_blocks = _parsing.find_code_blocks(content)
    if len(code_blocks) == 0:
        return None

    formatted_code_blocks = [_try_format_with_black(code_block.content) for code_block in code_blocks]
    if None in formatted_code_blocks:
        log.trace("Multiple code blocks detected but formatting failed for at least one code block.")
        return None

    non_code_blocks = _parsing.find_non_code_blocks(content)
    if len(formatted_code_blocks) + 1 != len(non_code_blocks):
        log.trace("Code blocks detected, but there are inconsistencies in what code blocks are detected.")
        return None

    fixed_markdown = _merge_non_code_blocks_with_code_blocks(non_code_blocks, formatted_code_blocks)
    if len(fixed_markdown) > constants.CodeBlock.maximum_auto_formatted_characters:
        log.trace("Automatically formatted message would be too large to post")
        return None

    return fixed_markdown
