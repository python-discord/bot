from __future__ import annotations

import logging
import re
import string
import textwrap
from collections import namedtuple
from typing import Collection, Iterable, Iterator, List, Optional, TYPE_CHECKING, Union

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from bot.utils.helpers import find_nth_occurrence
from . import MAX_SIGNATURE_AMOUNT
from ._html import get_dd_description, get_general_description, get_signatures
from ._markdown import DocMarkdownConverter
if TYPE_CHECKING:
    from ._cog import DocItem

log = logging.getLogger(__name__)

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
# Maximum discord message length - signatures on top - space for footer
_MAX_DESCRIPTION_LENGTH = 1900 - _MAX_SIGNATURES_LENGTH
_TRUNCATE_STRIP_CHARACTERS = "!?:;." + string.whitespace

BracketPair = namedtuple("BracketPair", ["opening_bracket", "closing_bracket"])
_BRACKET_PAIRS = {
    "{": BracketPair("{", "}"),
    "(": BracketPair("(", ")"),
    "[": BracketPair("[", "]"),
}


def _is_closing_quote(search_string: str, index: int) -> bool:
    """Check whether the quote at `index` inside `search_string` can be a closing quote."""
    if search_string[index - 1] != "\\":
        return True
    elif search_string[index - 2] == "\\":
        return True
    return False


def _split_parameters(parameters_string: str) -> Iterator[str]:
    """
    Split parameters of a signature into individual parameter strings on commas.

    Long string literals are not accounted for.
    """
    last_split = 0
    depth = 0
    current_search: Optional[BracketPair] = None
    quote_character = None

    enumerated_string = enumerate(parameters_string)
    for index, character in enumerated_string:
        if quote_character is None and character in _BRACKET_PAIRS:
            if current_search is None:
                current_search = _BRACKET_PAIRS[character]
                depth = 1
            elif character == current_search.opening_bracket:
                depth += 1

        elif character in {"'", '"'}:
            if current_search is not None:
                # We're currently searching for a bracket, skip all characters that belong to the string
                # to avoid false positives of closing brackets
                quote_character = character
                for index, character in enumerated_string:
                    if character == quote_character and _is_closing_quote(parameters_string, index):
                        break

            elif depth == 0:
                depth += 1
                quote_character = character
            elif character == quote_character:
                if _is_closing_quote(parameters_string, index):
                    depth -= 1
                if depth == 0:
                    quote_character = None

        elif current_search is not None and character == current_search.closing_bracket:
            depth -= 1
            if depth == 0:
                current_search = None

        elif depth == 0 and character == ",":
            yield parameters_string[last_split:index]
            last_split = index + 1

    yield parameters_string[last_split:]


def _truncate_signatures(signatures: Collection[str]) -> Union[List[str], Collection[str]]:
    """
    Truncate passed signatures to not exceed `_MAX_SIGNAUTRES_LENGTH`.

    If the signatures need to be truncated, parameters are collapsed until they fit withing the limit.
    Individual signatures can consist of max 1, 2, ..., `_MAX_SIGNATURE_AMOUNT` lines of text,
    inversely proportional to the amount of signatures.
    A maximum of `_MAX_SIGNATURE_AMOUNT` signatures is assumed to be passed.
    """
    if not sum(len(signature) for signature in signatures) > _MAX_SIGNATURES_LENGTH:
        return signatures

    max_signature_length = _EMBED_CODE_BLOCK_LINE_LENGTH * (MAX_SIGNATURE_AMOUNT + 1 - len(signatures))
    formatted_signatures = []
    for signature in signatures:
        signature = signature.strip()
        if len(signature) > max_signature_length:
            if (parameters_match := _PARAMETERS_RE.search(signature)) is None:
                formatted_signatures.append(textwrap.shorten(signature, max_signature_length))
                continue

            truncated_signature = []
            parameters_string = parameters_match[1]
            running_length = len(signature) - len(parameters_string)
            for parameter in _split_parameters(parameters_string):
                if (len(parameter) + running_length) <= max_signature_length - 4:  # account for comma and placeholder
                    truncated_signature.append(parameter)
                    running_length += len(parameter) + 1
                else:
                    truncated_signature.append(" ...")
                    formatted_signatures.append(signature.replace(parameters_string, ",".join(truncated_signature)))
                    break
        else:
            formatted_signatures.append(signature)

    return formatted_signatures


def _get_truncated_description(
        elements: Iterable[Union[Tag, NavigableString]],
        markdown_converter: DocMarkdownConverter,
        max_length: int,
        max_lines: int,
) -> str:
    """
    Truncate markdown from `elements` to be at most `max_length` characters when rendered or `max_lines` newlines.

    `max_length` limits the length of the rendered characters in the string,
    with the real string length limited to `_MAX_DESCRIPTION_LENGTH` to accommodate discord length limits
    """
    result = ""
    markdown_element_ends = []
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

    # Determine the "hard" truncation index.
    newline_truncate_index = find_nth_occurrence(result, "\n", max_lines)
    if newline_truncate_index is not None and newline_truncate_index < _MAX_DESCRIPTION_LENGTH:
        # Truncate based on maximum lines if there are more than the maximum number of lines.
        truncate_index = newline_truncate_index
    else:
        # There are less than the maximum number of lines; truncate based on the max char length.
        truncate_index = _MAX_DESCRIPTION_LENGTH

    # Nothing needs to be truncated if the last element ends before the truncation index.
    if truncate_index >= markdown_element_ends[-1]:
        return result

    # Determine the actual truncation index.
    possible_truncation_indices = [cut for cut in markdown_element_ends if cut < truncate_index]
    if not possible_truncation_indices:
        # In case there is no Markdown element ending before the truncation index, use shorten as a fallback.
        truncated_result = textwrap.shorten(result, truncate_index)
    else:
        # Truncate at the last Markdown element that comes before the truncation index.
        markdown_truncate_index = max(possible_truncation_indices)
        truncated_result = result[:markdown_truncate_index]

    return truncated_result.strip(_TRUNCATE_STRIP_CHARACTERS) + "..."


def _create_markdown(signatures: Optional[List[str]], description: Iterable[Tag], url: str) -> str:
    """
    Create a markdown string with the signatures at the top, and the converted html description below them.

    The signatures are wrapped in python codeblocks, separated from the description by a newline.
    The result markdown string is max 750 rendered characters for the description with signatures at the start.
    """
    description = _get_truncated_description(
        description,
        markdown_converter=DocMarkdownConverter(bullets="•", page_url=url),
        max_length=750,
        max_lines=13
    )
    description = _WHITESPACE_AFTER_NEWLINES_RE.sub('', description)
    if signatures is not None:
        formatted_markdown = "".join(f"```py\n{signature}```" for signature in _truncate_signatures(signatures))
    else:
        formatted_markdown = ""
    formatted_markdown += f"\n{description}"

    return formatted_markdown


def get_symbol_markdown(soup: BeautifulSoup, symbol_data: DocItem) -> Optional[str]:
    """
    Return parsed markdown of the passed symbol using the passed in soup, truncated to fit within a discord message.

    The method of parsing and what information gets included depends on the symbol's group.
    """
    symbol_heading = soup.find(id=symbol_data.symbol_id)
    if symbol_heading is None:
        return None
    signature = None
    # Modules, doc pages and labels don't point to description list tags but to tags like divs,
    # no special parsing can be done so we only try to include what's under them.
    if symbol_data.group in {"module", "doc", "label"} or symbol_heading.name != "dt":
        description = get_general_description(symbol_heading)

    elif symbol_data.group in _NO_SIGNATURE_GROUPS:
        description = get_dd_description(symbol_heading)

    else:
        signature = get_signatures(symbol_heading)
        description = get_dd_description(symbol_heading)
    return _create_markdown(signature, description, symbol_data.url).replace('¶', '').strip()
