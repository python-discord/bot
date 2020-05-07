import logging
from typing import Optional

from . import parsing

log = logging.getLogger(__name__)

PY_LANG_CODES = ("python", "py")  # Order is important; "py" is second cause it's a subset.
EXAMPLE_PY = "{lang}\nprint('Hello, world!')"  # Make sure to escape any Markdown symbols here.
EXAMPLE_CODE_BLOCKS = (
    "\\`\\`\\`{content}\n\\`\\`\\`\n\n"
    "**This will result in the following:**\n"
    "```{content}```"
)


def get_bad_ticks_message(code_block: parsing.CodeBlock) -> Optional[str]:
    """Return instructions on using the correct ticks for `code_block`."""
    log.trace("Creating instructions for incorrect code block ticks.")
    valid_ticks = f"\\{parsing.BACKTICK}" * 3

    # The space at the end is important here because something may be appended!
    instructions = (
        "It looks like you are trying to paste code into this channel.\n\n"
        "You seem to be using the wrong symbols to indicate where the code block should start. "
        f"The correct symbols would be {valid_ticks}, not `{code_block.tick * 3}`. "
    )

    log.trace("Check if the bad ticks code block also has issues with the language specifier.")
    addition_msg = get_bad_lang_message(code_block.content)
    if not addition_msg:
        addition_msg = get_no_lang_message(code_block.content)

    # Combine the back ticks message with the language specifier message. The latter will
    # already have an example code block.
    if addition_msg:
        log.trace("Language specifier issue found; appending additional instructions.")

        # The first line has a double line break which is not desirable when appending the msg.
        addition_msg = addition_msg.replace("\n\n", " ", 1)

        # Make the first character of the addition lower case.
        instructions += "\n\nFurthermore, " + addition_msg[0].lower() + addition_msg[1:]
    else:
        log.trace("No issues with the language specifier found.")

        # Determine the example code to put in the code block based on the language specifier.
        if code_block.language.lower() in PY_LANG_CODES:
            log.trace(f"Code block has a Python language specifier `{code_block.language}`.")
            content = EXAMPLE_PY.format(lang=code_block.language)
        elif code_block.language:
            log.trace(f"Code block has a foreign language specifier `{code_block.language}`.")
            # It's not feasible to determine what would be a valid example for other languages.
            content = f"{code_block.language}\n..."
        else:
            log.trace("Code block has no language specifier (and the code isn't valid Python).")
            content = "Hello, world!"

        example_blocks = EXAMPLE_CODE_BLOCKS.format(content=content)
        instructions += f"\n\n**Here is an example of how it should look:**\n{example_blocks}"

    return instructions


def get_no_ticks_message(content: str) -> Optional[str]:
    """If `content` is Python/REPL code, return instructions on using code blocks."""
    log.trace("Creating instructions for a missing code block.")

    if parsing.is_repl_code(content) or parsing.is_python_code(content):
        example_blocks = EXAMPLE_CODE_BLOCKS.format(content=EXAMPLE_PY.format(lang="python"))
        return (
            "It looks like you're trying to paste code into this channel.\n\n"
            "Discord has support for Markdown, which allows you to post code with full "
            "syntax highlighting. Please use these whenever you paste code, as this "
            "helps improve the legibility and makes it easier for us to help you.\n\n"
            f"**To do this, use the following method:**\n{example_blocks}"
        )
    else:
        log.trace("Aborting missing code block instructions: content is not Python code.")


def get_bad_lang_message(content: str) -> Optional[str]:
    """
    Return instructions on fixing the Python language specifier for a code block.

    If `content` doesn't start with "python" or "py" as the language specifier, return None.
    """
    log.trace("Creating instructions for a poorly specified language.")

    stripped = content.lstrip().lower()
    lang = next((lang for lang in PY_LANG_CODES if stripped.startswith(lang)), None)

    if lang:
        # Note that get_bad_ticks_message expects the first line to have an extra newline.
        lines = ["It looks like you incorrectly specified a language for your code block.\n"]

        if content.startswith(" "):
            log.trace("Language specifier was preceded by a space.")
            lines.append(f"Make sure there are no spaces between the back ticks and `{lang}`.")

        if stripped[len(lang)] != "\n":
            log.trace("Language specifier was not followed by a newline.")
            lines.append(
                f"Make sure you put your code on a new line following `{lang}`. "
                f"There must not be any spaces after `{lang}`."
            )

        example_blocks = EXAMPLE_CODE_BLOCKS.format(content=EXAMPLE_PY.format(lang=lang))
        lines.append(f"\n**Here is an example of how it should look:**\n{example_blocks}")

        return "\n".join(lines)
    else:
        log.trace("Aborting bad language instructions: language specified isn't Python.")


def get_no_lang_message(content: str) -> Optional[str]:
    """
    Return instructions on specifying a language for a code block.

    If `content` is not valid Python or Python REPL code, return None.
    """
    log.trace("Creating instructions for a missing language.")

    if parsing.is_repl_code(content) or parsing.is_python_code(content):
        example_blocks = EXAMPLE_CODE_BLOCKS.format(content=EXAMPLE_PY.format(lang="python"))

        # Note that get_bad_ticks_message expects the first line to have an extra newline.
        return (
            "It looks like you pasted Python code without syntax highlighting.\n\n"
            "Please use syntax highlighting to improve the legibility of your code and make "
            "it easier for us to help you.\n\n"
            f"**To do this, use the following method:**\n{example_blocks}"
        )
    else:
        log.trace("Aborting missing language instructions: content is not Python code.")
