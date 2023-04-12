from __future__ import annotations

import re
import string
import textwrap
from collections import namedtuple
from collections.abc import Collection, Iterable, Iterator
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from bot.log import get_logger
from bot.utils.helpers import find_nth_occurrence

from . import MAX_SIGNATURE_AMOUNT
from ._html import get_dd_description, get_general_description, get_signatures
from ._markdown import DocMarkdownConverter

if TYPE_CHECKING:
    from ._cog import DocItem

log = get_logger(__name__)

_WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)(\s+)")
_PARAMETERS_RE = re.compile(r"\((.+)\)")

_NO_SIGNATURE_GROUPS = {
    "attribute",
    "envvar",
    "setting",
    "tempaltefilter",
    "templatetag",
    "term",
}
_EMBED_CODE_BLOCK_LINE_LENGTH = 61
# _MAX_SIGNATURE_AMOUNT code block wrapped lines with py syntax highlight
_MAX_SIGNATURES_LENGTH = (_EMBED_CODE_BLOCK_LINE_LENGTH + 8) * MAX_SIGNATURE_AMOUNT
# Maximum embed description length - signatures on top
_MAX_DESCRIPTION_LENGTH = 4096 - _MAX_SIGNATURES_LENGTH
_TRUNCATE_STRIP_CHARACTERS = "!?:;." + string.whitespace

BracketPair = namedtuple("BracketPair", ["opening_bracket", "closing_bracket"])
_BRACKET_PAIRS = {
    "{": BracketPair("{", "}"),
    "(": BracketPair("(", ")"),
    "[": BracketPair("[", "]"),
    "<": BracketPair("<", ">"),
}


def _split_parameters(parameters_string: str) -> Iterator[str]:
    """
    Split parameters of a signature into individual parameter strings on commas.

    Long string literals are not accounted for.
    """
    last_split = 0
    depth = 0
    current_search: BracketPair | None = None

    enumerated_string = enumerate(parameters_string)
    for index, character in enumerated_string:
        if character in {"'", '"'}:
            # Skip everything inside of strings, regardless of the depth.
            quote_character = character  # The closing quote must equal the opening quote.
            preceding_backslashes = 0
            for _, character in enumerated_string:
                # If an odd number of backslashes precedes the quote, it was escaped.
                if character == quote_character and not preceding_backslashes % 2:
                    break
                if character == "\\":
                    preceding_backslashes += 1
                else:
                    preceding_backslashes = 0

        elif current_search is None:
            if (current_search := _BRACKET_PAIRS.get(character)) is not None:
                depth = 1
            elif character == ",":
                yield parameters_string[last_split:index]
                last_split = index + 1

        else:
            if character == current_search.opening_bracket:
                depth += 1

            elif character == current_search.closing_bracket:
                depth -= 1
                if depth == 0:
                    current_search = None

    yield parameters_string[last_split:]


def _truncate_signatures(signatures: Collection[str]) -> list[str] | Collection[str]:
    """
    Truncate passed signatures to not exceed `_MAX_SIGNATURES_LENGTH`.

    If the signatures need to be truncated, parameters are collapsed until they fit withing the limit.
    Individual signatures can consist of max 1, 2, ..., `_MAX_SIGNATURE_AMOUNT` lines of text,
    inversely proportional to the amount of signatures.
    A maximum of `_MAX_SIGNATURE_AMOUNT` signatures is assumed to be passed.
    """
    if sum(len(signature) for signature in signatures) <= _MAX_SIGNATURES_LENGTH:
        # Total length of signatures is under the length limit; no truncation needed.
        return signatures

    max_signature_length = _EMBED_CODE_BLOCK_LINE_LENGTH * (MAX_SIGNATURE_AMOUNT + 1 - len(signatures))
    formatted_signatures = []
    for signature in signatures:
        signature = signature.strip()
        if len(signature) > max_signature_length:
            if (parameters_match := _PARAMETERS_RE.search(signature)) is None:
                # The signature has no parameters or the regex failed; perform a simple truncation of the text.
                formatted_signatures.append(textwrap.shorten(signature, max_signature_length, placeholder="..."))
                continue

            truncated_signature = []
            parameters_string = parameters_match[1]
            running_length = len(signature) - len(parameters_string)
            for parameter in _split_parameters(parameters_string):
                # Check if including this parameter would still be within the maximum length.
                if (len(parameter) + running_length) <= max_signature_length - 5:  # account for comma and placeholder
                    truncated_signature.append(parameter)
                    running_length += len(parameter) + 1
                else:
                    # There's no more room for this parameter. Truncate the parameter list and put it in the signature.
                    truncated_signature.append(" ...")
                    formatted_signatures.append(signature.replace(parameters_string, ",".join(truncated_signature)))
                    break
        else:
            # The current signature is under the length limit; no truncation needed.
            formatted_signatures.append(signature)

    return formatted_signatures


def _get_truncated_description(
    elements: Iterable[Tag | NavigableString],
    markdown_converter: DocMarkdownConverter,
    max_length: int,
    max_lines: int,
) -> str:
    """
    Truncate the Markdown from `elements` to be at most `max_length` characters when rendered or `max_lines` newlines.

    `max_length` limits the length of the rendered characters in the string,
    with the real string length limited to `_MAX_DESCRIPTION_LENGTH` to accommodate discord length limits.
    """
    result = ""
    markdown_element_ends = []  # Stores indices into `result` which point to the end boundary of each Markdown element.
    rendered_length = 0

    tag_end_index = 0
    for element in elements:
        is_tag = isinstance(element, Tag)
        element_length = len(element.text) if is_tag else len(element)

        if rendered_length + element_length < max_length:
            if is_tag:
                element_markdown = markdown_converter.process_tag(element, convert_as_inline=False)
            else:
                element_markdown = markdown_converter.process_text(element)

            rendered_length += element_length
            tag_end_index += len(element_markdown)

            if not element_markdown.isspace():
                markdown_element_ends.append(tag_end_index)
            result += element_markdown
        else:
            break

    if not markdown_element_ends:
        return ""

    # Determine the "hard" truncation index. Account for the ellipsis placeholder for the max length.
    newline_truncate_index = find_nth_occurrence(result, "\n", max_lines)
    if newline_truncate_index is not None and newline_truncate_index < _MAX_DESCRIPTION_LENGTH - 3:
        # Truncate based on maximum lines if there are more than the maximum number of lines.
        truncate_index = newline_truncate_index
    else:
        # There are less than the maximum number of lines; truncate based on the max char length.
        truncate_index = _MAX_DESCRIPTION_LENGTH - 3

    # Nothing needs to be truncated if the last element ends before the truncation index.
    if truncate_index >= markdown_element_ends[-1]:
        return result

    # Determine the actual truncation index.
    possible_truncation_indices = [cut for cut in markdown_element_ends if cut < truncate_index]
    if not possible_truncation_indices:
        # In case there is no Markdown element ending before the truncation index, try to find a good cutoff point.
        force_truncated = result[:truncate_index]
        # If there is an incomplete codeblock, cut it out.
        if force_truncated.count("```") % 2:
            force_truncated = force_truncated[:force_truncated.rfind("```")]
        # Search for substrings to truncate at, with decreasing desirability.
        for string_ in ("\n\n", "\n", ". ", ", ", ",", " "):
            cutoff = force_truncated.rfind(string_)

            if cutoff != -1:
                truncated_result = force_truncated[:cutoff]
                break
        else:
            truncated_result = force_truncated

    else:
        # Truncate at the last Markdown element that comes before the truncation index.
        markdown_truncate_index = possible_truncation_indices[-1]
        truncated_result = result[:markdown_truncate_index]

    return truncated_result.strip(_TRUNCATE_STRIP_CHARACTERS) + "..."


def _create_markdown(signatures: list[str] | None, description: Iterable[Tag], url: str) -> str:
    """
    Create a Markdown string with the signatures at the top, and the converted html description below them.

    The signatures are wrapped in python codeblocks, separated from the description by a newline.
    The result Markdown string is max 750 rendered characters for the description with signatures at the start.
    """
    description = _get_truncated_description(
        description,
        markdown_converter=DocMarkdownConverter(bullets="•", page_url=url),
        max_length=750,
        max_lines=13
    )
    description = _WHITESPACE_AFTER_NEWLINES_RE.sub("", description)
    if signatures is not None:
        signature = "".join(f"```py\n{signature}```" for signature in _truncate_signatures(signatures))
        return f"{signature}\n{description}"
    return description


def get_symbol_markdown(soup: BeautifulSoup, symbol_data: DocItem) -> str | None:
    """
    Return parsed Markdown of the passed item using the passed in soup, truncated to fit within a discord message.

    The method of parsing and what information gets included depends on the symbol's group.
    """
    symbol_heading = soup.find(id=symbol_data.symbol_id)
    if symbol_heading is None:
        return None
    signature = None
    # Modules, doc pages and labels don't point to description list tags but to tags like divs,
    # no special parsing can be done so we only try to include what's under them.
    if symbol_heading.name != "dt":
        description = get_general_description(symbol_heading)

    elif symbol_data.group in _NO_SIGNATURE_GROUPS:
        description = get_dd_description(symbol_heading)

    else:
        signature = get_signatures(symbol_heading)
        description = get_dd_description(symbol_heading)

    for description_element in description:
        if isinstance(description_element, Tag):
            for tag in description_element.find_all("a", class_="headerlink"):
                tag.decompose()

    return _create_markdown(signature, description, symbol_data.url).strip()
