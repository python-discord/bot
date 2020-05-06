import logging
from typing import Optional

from . import parsing

log = logging.getLogger(__name__)

PY_LANG_CODES = ("python", "py")
EXAMPLE_PY = f"python\nprint('Hello, world!')"  # Make sure to escape any Markdown symbols here.
EXAMPLE_CODE_BLOCKS = (
    "\\`\\`\\`{content}\n\\`\\`\\`\n\n"
    "**This will result in the following:**\n"
    "```{content}```"
)


def get_bad_ticks_message(code_block: parsing.CodeBlock) -> Optional[str]:
    """Return instructions on using the correct ticks for `code_block`."""
    valid_ticks = f"\\{parsing.BACKTICK}" * 3

    # The space at the end is important here because something may be appended!
    instructions = (
        "It looks like you are trying to paste code into this channel.\n\n"
        "You seem to be using the wrong symbols to indicate where the code block should start. "
        f"The correct symbols would be {valid_ticks}, not `{code_block.tick * 3}`. "
    )

    # Check if the code has an issue with the language specifier.
    addition_msg = get_bad_lang_message(code_block.content)
    if not addition_msg:
        addition_msg = get_no_lang_message(code_block.content)

    # Combine the back ticks message with the language specifier message. The latter will
    # already have an example code block.
    if addition_msg:
        # The first line has a double line break which is not desirable when appending the msg.
        addition_msg = addition_msg.replace("\n\n", " ", 1)

        # Make the first character of the addition lower case.
        instructions += "\n\nFurthermore, " + addition_msg[0].lower() + addition_msg[1:]
    else:
        # Determine the example code to put in the code block based on the language specifier.
        if code_block.language.lower() in PY_LANG_CODES:
            content = EXAMPLE_PY
        elif code_block.language:
            # It's not feasible to determine what would be a valid example for other languages.
            content = f"{code_block.language}\n..."
        else:
            content = "Hello, world!"

        example_blocks = EXAMPLE_CODE_BLOCKS.format(content=content)
        instructions += f"\n\n**Here is an example of how it should look:**\n{example_blocks}"

    return instructions


def get_no_ticks_message(content: str) -> Optional[str]:
    """If `content` is Python/REPL code, return instructions on using code blocks."""
    if parsing.is_repl_code(content) or parsing.is_python_code(content):
        example_blocks = EXAMPLE_CODE_BLOCKS.format(content=EXAMPLE_PY)
        return (
            "It looks like you're trying to paste code into this channel.\n\n"
            "Discord has support for Markdown, which allows you to post code with full "
            "syntax highlighting. Please use these whenever you paste code, as this "
            "helps improve the legibility and makes it easier for us to help you.\n\n"
            f"**To do this, use the following method:**\n{example_blocks}"
        )


def get_bad_lang_message(content: str) -> Optional[str]:
    """
    Return instructions on fixing the Python language specifier for a code block.

    If `content` doesn't start with "python" or "py" as the language specifier, return None.
    """
    stripped = content.lstrip().lower()
    lang = next((lang for lang in PY_LANG_CODES if stripped.startswith(lang)), None)

    if lang:
        # Note that get_bad_ticks_message expects the first line to have an extra newline.
        lines = ["It looks like you incorrectly specified a language for your code block.\n"]

        if content.startswith(" "):
            lines.append(f"Make sure there are no spaces between the back ticks and `{lang}`.")

        if stripped[len(lang)] != "\n":
            lines.append(
                f"Make sure you put your code on a new line following `{lang}`. "
                f"There must not be any spaces after `{lang}`."
            )

        example_blocks = EXAMPLE_CODE_BLOCKS.format(content=EXAMPLE_PY)
        lines.append(f"\n**Here is an example of how it should look:**\n{example_blocks}")

        return "\n".join(lines)


def get_no_lang_message(content: str) -> Optional[str]:
    """
    Return instructions on specifying a language for a code block.

    If `content` is not valid Python or Python REPL code, return None.
    """
    if parsing.is_repl_code(content) or parsing.is_python_code(content):
        example_blocks = EXAMPLE_CODE_BLOCKS.format(content=EXAMPLE_PY)

        # Note that get_bad_ticks_message expects the first line to have an extra newline.
        return (
            "It looks like you pasted Python code without syntax highlighting.\n\n"
            "Please use syntax highlighting to improve the legibility of your code and make "
            "it easier for us to help you.\n\n"
            f"**To do this, use the following method:**\n{example_blocks}"
        )
