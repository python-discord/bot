import black

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


def try_fix_markdown(content: str) -> str | None:
    """
    Converts the user's content to a properly formatted Markdown message.

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

    if len(formatted_code_blocks) == 1:
        return f"Your code correctly formatted:\n{_code_as_markdown(formatted_code_blocks[0])}"

    return "Your codes correctly formatted:\n" + "\n".join(
        f"Codeblock {i}:\n{_code_as_markdown(formatted_code_block)}"
        for i, formatted_code_block in enumerate(formatted_code_blocks, start=1)
    )
