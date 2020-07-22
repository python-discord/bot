import logging
import re
import string
from functools import partial
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


class DocMarkdownConverter(MarkdownConverter):
    """Subclass markdownify's MarkdownCoverter to provide custom conversion methods."""

    def __init__(self, *, page_url: str, **options):
        super().__init__(**options)
        self.page_url = page_url

    def convert_code(self, el: PageElement, text: str) -> str:
        """Undo `markdownify`s underscore escaping."""
        return f"`{text}`".replace('\\', '')

    def convert_pre(self, el: PageElement, text: str) -> str:
        """Wrap any codeblocks in `py` for syntax highlighting."""
        code = ''.join(el.strings)
        return f"```py\n{code}```"

    def convert_a(self, el: PageElement, text: str) -> str:
        """Resolve relative URLs to `self.page_url`."""
        el["href"] = urljoin(self.page_url, el["href"])
        return super().convert_a(el, text)

    def convert_p(self, el: PageElement, text: str) -> str:
        """Include only one newline instead of two when the parent is a li tag."""
        parent = el.parent
        if parent is not None and parent.name == "li":
            return f"{text}\n"
        return super().convert_p(el, text)


def markdownify(html: str, *, url: str = "") -> str:
    """Create a DocMarkdownConverter object from the input html."""
    return DocMarkdownConverter(bullets='•', page_url=url).convert(html)


def find_elements_until_tag(
        start_element: PageElement,
        tag_filter: Union[Tuple[str, ...], Callable[[Tag], bool]],
        *,
        func: Callable,
        limit: int = None,
) -> List[Tag]:
    """
    Get all tags until a tag matching `tag_filter` is found.

    `tag_filter` can be either a tuple of string names to check against,
    or a filtering t.Callable that's applied to the tags.

    `func` takes in a BeautifulSoup unbound method for finding multiple elements, such as `BeautifulSoup.find_all`.
    That method is then iterated over and all tags until the matching tag are added to the return list as strings.
    """
    elements = []

    for element in func(start_element, limit=limit):
        if isinstance(tag_filter, tuple):
            if element.name in tag_filter:
                break
        elif tag_filter(element):
            break
        elements.append(element)

    return elements


find_next_children_until_tag = partial(find_elements_until_tag, func=partial(BeautifulSoup.find_all, recursive=False))
find_next_siblings_until_tag = partial(find_elements_until_tag, func=BeautifulSoup.find_next_siblings)
find_previous_siblings_until_tag = partial(find_elements_until_tag, func=BeautifulSoup.find_previous_siblings)


def get_module_description(start_element: PageElement) -> Optional[str]:
    """
    Get page content to a table or a tag with its class in `SEARCH_END_TAG_ATTRS`.

    A headerlink a tag is attempted to be found to skip repeating the module name in the description,
    if it's found it's used as the tag to search from instead of the `start_element`.
    """
    header = start_element.find("a", attrs={"class": "headerlink"})
    start_tag = header.parent if header is not None else start_element
    description = "".join(str(tag) for tag in find_next_siblings_until_tag(start_tag, _match_end_tag))

    return description


def get_signatures(start_signature: PageElement) -> List[str]:
    """
    Collect up to 3 signatures from dt tags around the `start_signature` dt tag.

    First the signatures under the `start_signature` are included;
    if less than 2 are found, tags above the start signature are added to the result if any are present.
    """
    signatures = []
    for element in (
            *reversed(find_previous_siblings_until_tag(start_signature, ("dd",), limit=2)),
            start_signature,
            *find_next_siblings_until_tag(start_signature, ("dd",), limit=2),
    )[-3:]:
        signature = UNWANTED_SIGNATURE_SYMBOLS_RE.sub("", element.text)

        if signature:
            signatures.append(signature)

    return signatures


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
