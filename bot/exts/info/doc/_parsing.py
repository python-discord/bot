from __future__ import annotations

import logging
import re
import string
import textwrap
from functools import partial
from typing import Callable, Collection, Container, Iterable, List, Optional, TYPE_CHECKING, Union

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, Tag

from bot.utils.helpers import find_nth_occurrence
from ._html import Strainer
from ._markdown import DocMarkdownConverter
if TYPE_CHECKING:
    from ._cog import DocItem

log = logging.getLogger(__name__)

_MAX_SIGNATURE_AMOUNT = 3

_UNWANTED_SIGNATURE_SYMBOLS_RE = re.compile(r"\[source]|\\\\|¶")
_WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)(\s+)")
_PARAMETERS_RE = re.compile(r"\((.+)\)")

_SEARCH_END_TAG_ATTRS = (
    "data",
    "function",
    "class",
    "exception",
    "seealso",
    "section",
    "rubric",
    "sphinxsidebar",
)

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
_MAX_SIGNATURES_LENGTH = (_EMBED_CODE_BLOCK_LINE_LENGTH + 8) * _MAX_SIGNATURE_AMOUNT
# Maximum discord message length - signatures on top
_MAX_DESCRIPTION_LENGTH = 2000 - _MAX_SIGNATURES_LENGTH
_TRUNCATE_STRIP_CHARACTERS = "!?:;." + string.whitespace
_BRACKET_PAIRS = {
    "{": "}",
    "(": ")",
    "[": "]",
}


def _split_parameters(parameters_string: str) -> List[str]:
    """
    Split parameters of a signature into individual parameter strings on commas.

    Long string literals are not accounted for.
    """
    parameters_list = []
    last_split = 0
    depth = 0
    expected_end = None
    current_search = None

    for index, character in enumerate(parameters_string):
        if character in _BRACKET_PAIRS:
            if current_search is None:
                current_search = character
                expected_end = _BRACKET_PAIRS[character]
            if character == current_search:
                depth += 1

        elif character in {"'", '"'}:
            if depth == 0:
                depth += 1
            elif parameters_string[index-1] != "\\":
                depth -= 1
            elif parameters_string[index-2] == "\\":
                depth -= 1

        elif character == expected_end:
            depth -= 1
            if depth == 0:
                current_search = None
                expected_end = None

        elif depth == 0 and character == ",":
            parameters_list.append(parameters_string[last_split:index])
            last_split = index + 1

    parameters_list.append(parameters_string[last_split:])
    return parameters_list


def _find_elements_until_tag(
        start_element: PageElement,
        end_tag_filter: Union[Container[str], Callable[[Tag], bool]],
        *,
        func: Callable,
        include_strings: bool = False,
        limit: int = None,
) -> List[Union[Tag, NavigableString]]:
    """
    Get all elements up to `limit` or until a tag matching `tag_filter` is found.

    `end_tag_filter` can be either a container of string names to check against,
    or a filtering callable that's applied to tags.

    When `include_strings` is True, `NavigableString`s from the document will be included in the result along `Tag`s.

    `func` takes in a BeautifulSoup unbound method for finding multiple elements, such as `BeautifulSoup.find_all`.
    The method is then iterated over and all elements until the matching tag or the limit are added to the return list.
    """
    use_container_filter = not callable(end_tag_filter)
    elements = []

    for element in func(start_element, name=Strainer(include_strings=include_strings), limit=limit):
        if isinstance(element, Tag):
            if use_container_filter:
                if element.name in end_tag_filter:
                    break
            elif end_tag_filter(element):
                break
        elements.append(element)

    return elements


_find_next_children_until_tag = partial(_find_elements_until_tag, func=partial(BeautifulSoup.find_all, recursive=False))
_find_recursive_children_until_tag = partial(_find_elements_until_tag, func=BeautifulSoup.find_all)
_find_next_siblings_until_tag = partial(_find_elements_until_tag, func=BeautifulSoup.find_next_siblings)
_find_previous_siblings_until_tag = partial(_find_elements_until_tag, func=BeautifulSoup.find_previous_siblings)


def _get_general_description(start_element: Tag) -> List[Union[Tag, NavigableString]]:
    """
    Get page content to a table or a tag with its class in `SEARCH_END_TAG_ATTRS`.

    A headerlink a tag is attempted to be found to skip repeating the symbol information in the description,
    if it's found it's used as the tag to start the search from instead of the `start_element`.
    """
    child_tags = _find_recursive_children_until_tag(start_element, _class_filter_factory(["section"]), limit=100)
    header = next(filter(_class_filter_factory(["headerlink"]), child_tags), None)
    start_tag = header.parent if header is not None else start_element
    return _find_next_siblings_until_tag(start_tag, _class_filter_factory(_SEARCH_END_TAG_ATTRS), include_strings=True)


def _get_dd_description(symbol: PageElement) -> List[Union[Tag, NavigableString]]:
    """Get the contents of the next dd tag, up to a dt or a dl tag."""
    description_tag = symbol.find_next("dd")
    return _find_next_children_until_tag(description_tag, ("dt", "dl"), include_strings=True)


def _get_signatures(start_signature: PageElement) -> List[str]:
    """
    Collect up to `_MAX_SIGNATURE_AMOUNT` signatures from dt tags around the `start_signature` dt tag.

    First the signatures under the `start_signature` are included;
    if less than 2 are found, tags above the start signature are added to the result if any are present.
    """
    signatures = []
    for element in (
            *reversed(_find_previous_siblings_until_tag(start_signature, ("dd",), limit=2)),
            start_signature,
            *_find_next_siblings_until_tag(start_signature, ("dd",), limit=2),
    )[-(_MAX_SIGNATURE_AMOUNT):]:
        signature = _UNWANTED_SIGNATURE_SYMBOLS_RE.sub("", element.text)

        if signature:
            signatures.append(signature)

    return signatures


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

    max_signature_length = _EMBED_CODE_BLOCK_LINE_LENGTH * (_MAX_SIGNATURE_AMOUNT + 1 - len(signatures))
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
                element_markdown = markdown_converter.process_tag(element)
            else:
                element_markdown = markdown_converter.process_text(element)

            element_markdown_length = len(element_markdown)
            rendered_length += element_length
            tag_end_index += element_markdown_length

            if not element_markdown.isspace():
                markdown_element_ends.append(tag_end_index)
            result += element_markdown
        else:
            break

    if not markdown_element_ends:
        return ""

    newline_truncate_index = find_nth_occurrence(result, "\n", max_lines)
    if newline_truncate_index is not None and newline_truncate_index < _MAX_DESCRIPTION_LENGTH:
        truncate_index = newline_truncate_index
    else:
        truncate_index = _MAX_DESCRIPTION_LENGTH

    if truncate_index >= markdown_element_ends[-1]:
        return result

    markdown_truncate_index = max(cut for cut in markdown_element_ends if cut < truncate_index)
    return result[:markdown_truncate_index].strip(_TRUNCATE_STRIP_CHARACTERS) + "..."


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


def _class_filter_factory(class_names: Iterable[str]) -> Callable[[Tag], bool]:
    """Create callable that returns True when the passed in tag's class is in `class_names` or when it's is a table."""
    def match_tag(tag: Tag) -> bool:
        for attr in class_names:
            if attr in tag.get("class", ()):
                return True
        return tag.name == "table"

    return match_tag


def get_symbol_markdown(soup: BeautifulSoup, symbol_data: DocItem) -> Optional[str]:
    """
    Return parsed markdown of the passed symbol using the passed in soup, truncated to 1000 characters.

    The method of parsing and what information gets included depends on the symbol's group.
    """
    symbol_heading = soup.find(id=symbol_data.symbol_id)
    if symbol_heading is None:
        log.warning("Symbol present in loaded inventories not found on site, consider refreshing inventories.")
        return None
    signature = None
    # Modules, doc pages and labels don't point to description list tags but to tags like divs,
    # no special parsing can be done so we only try to include what's under them.
    if symbol_data.group in {"module", "doc", "label"} or symbol_heading.name != "dt":
        description = _get_general_description(symbol_heading)

    elif symbol_data.group in _NO_SIGNATURE_GROUPS:
        description = _get_dd_description(symbol_heading)

    else:
        signature = _get_signatures(symbol_heading)
        description = _get_dd_description(symbol_heading)
    return _create_markdown(signature, description, symbol_data.url).replace('¶', '')
