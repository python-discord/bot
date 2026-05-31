from collections.abc import Sequence

import black

from bot.exts.info.codeblock import _parsing
from bot.exts.info.codeblock._parsing import CodeBlock
from bot.log import get_logger

log = get_logger(__name__)


def _code_as_markdown(code: str) -> str:
    return f"{_parsing.BACKTICK * 3}py\n{code}\n{_parsing.BACKTICK * 3}"


def _try_format_with_black(code: str) -> str | None:
    try:
        return black.format_str(code, mode=black.FileMode())
    except Exception:
        log.trace("automatic formatting failed")
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


def attempt_formatting(content: str, code_blocks: Sequence[CodeBlock]) -> str | None:
    formatted_content = _attempt_formatting_whole_content(content)
    if formatted_content is not None:
        return _code_as_markdown(formatted_content)

    formatted_code_blocks = [_try_format_with_black(code_block.content) for code_block in code_blocks]
    if None in formatted_code_blocks:
        log.trace("Multiple code blocks detected but formatting failed for at least one code block.")
        return None

    return "\n".join(
        f"Code {i}:\n{_code_as_markdown(formatted_code_block)}"
        for i, formatted_code_block in enumerate(formatted_code_blocks, start=1)
    )
