import logging
import re
import string
from typing import Callable, List, Optional, Tuple, Union

from aiohttp import ClientSession
from bs4 import BeautifulSoup
from bs4.element import PageElement, Tag

from .cache import async_cache

log = logging.getLogger(__name__)

UNWANTED_SIGNATURE_SYMBOLS_RE = re.compile(r"\[source]|\\\\|¶")
SEARCH_END_TAG_ATTRS = (
    "data",
    "function",
    "class",
    "exception",
    "seealso",
    "section",
    "rubric",
    "sphinxsidebar",
)


def parse_module_symbol(heading: PageElement) -> Optional[Tuple[None, str]]:
    """Get page content from the headerlink up to a table or a tag with its class in `SEARCH_END_TAG_ATTRS`."""
    start_tag = heading.find("a", attrs={"class": "headerlink"})
    if start_tag is None:
        return None

    description = find_all_children_until_tag(start_tag, _match_end_tag)
    if description is None:
        return None

    return None, description


def parse_symbol(heading: PageElement, html: str) -> Tuple[List[str], str]:
    """
    Parse the signatures and description of a symbol.

    Collects up to 3 signatures from dt tags and a description from their sibling dd tag.
    """
    signatures = []
    description_element = heading.find_next_sibling("dd")
    description_pos = html.find(str(description_element))
    description = find_all_children_until_tag(description_element, tag_filter=("dt", "dl"))

    for element in (
            *reversed(heading.find_previous_siblings("dt", limit=2)),
            heading,
            *heading.find_next_siblings("dt", limit=2),
    )[-3:]:
        signature = UNWANTED_SIGNATURE_SYMBOLS_RE.sub("", element.text)

        if signature and html.find(str(element)) < description_pos:
            signatures.append(signature)

    return signatures, description


def find_all_children_until_tag(
        start_element: PageElement,
        tag_filter: Union[Tuple[str, ...], Callable[[Tag], bool]]
) -> Optional[str]:
    """
    Get all direct children until a child matching `tag_filter` is found.

    `tag_filter` can be either a tuple of string names to check against,
    or a filtering callable that's applied to the tags.
    """
    text = ""

    for element in start_element.find_next().find_next_siblings():
        if isinstance(tag_filter, tuple):
            if element.name in tag_filter:
                break
        elif tag_filter(element):
            break
        text += str(element)

    return text


def truncate_markdown(markdown: str, max_length: int) -> str:
    """
    Truncate `markdown` to be at most `max_length` characters.

    The markdown string is searched for substrings to cut at, to keep its structure,
    but if none are found the string is simply sliced.
    """
    if len(markdown) > max_length:
        shortened = markdown[:max_length]
        description_cutoff = shortened.rfind('\n\n', 100)
        if description_cutoff == -1:
            # Search the shortened version for cutoff points in decreasing desirability,
            # cutoff at 1000 if none are found.
            for cutoff_string in (". ", ", ", ",", " "):
                description_cutoff = shortened.rfind(cutoff_string)
                if description_cutoff != -1:
                    break
            else:
                description_cutoff = max_length
        markdown = markdown[:description_cutoff]

        # If there is an incomplete code block, cut it out
        if markdown.count("```") % 2:
            codeblock_start = markdown.rfind('```py')
            markdown = markdown[:codeblock_start].rstrip()
        markdown = markdown.rstrip(string.punctuation) + "..."
    return markdown


@async_cache(arg_offset=1)
async def get_soup_from_url(http_session: ClientSession, url: str) -> BeautifulSoup:
    """Create a BeautifulSoup object from the HTML data in `url` with the head tag removed."""
    log.trace(f"Sending a request to {url}.")
    async with http_session.get(url) as response:
        soup = BeautifulSoup(await response.text(encoding="utf8"), 'lxml')
    soup.find("head").decompose()  # the head contains no useful data so we can remove it
    return soup


def _match_end_tag(tag: Tag) -> bool:
    """Matches `tag` if its class value is in `SEARCH_END_TAG_ATTRS` or the tag is table."""
    for attr in SEARCH_END_TAG_ATTRS:
        if attr in tag.get("class", ()):
            return True

    return tag.name == "table"
