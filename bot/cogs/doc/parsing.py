import logging
import re
import string
import textwrap
from functools import partial
from typing import Callable, List, Optional, TYPE_CHECKING, Tuple, Union
from urllib.parse import urljoin

from aiohttp import ClientSession
from bs4 import BeautifulSoup
from bs4.element import PageElement, Tag
from markdownify import MarkdownConverter

from .cache import async_cache
if TYPE_CHECKING:
    from .cog import DocItem

log = logging.getLogger(__name__)

_UNWANTED_SIGNATURE_SYMBOLS_RE = re.compile(r"\[source]|\\\\|¶")
_WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)(\s+)")

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


class _DocMarkdownConverter(MarkdownConverter):
    """Subclass markdownify's MarkdownCoverter to provide custom conversion methods."""

    def __init__(self, *, page_url: str, **options):
        super().__init__(**options)
        self.page_url = page_url

    def convert_li(self, el: PageElement, text: str) -> str:
        """Fix markdownify's erroneous indexing in ol tags."""
        parent = el.parent
        if parent is not None and parent.name == 'ol':
            li_tags = parent.find_all("li")
            bullet = '%s.' % (li_tags.index(el)+1)
        else:
            depth = -1
            while el:
                if el.name == 'ul':
                    depth += 1
                el = el.parent
            bullets = self.options['bullets']
            bullet = bullets[depth % len(bullets)]
        return '%s %s\n' % (bullet, text or '')

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


def _markdownify(html: str, *, url: str = "") -> str:
    """Create a DocMarkdownConverter object from the input html."""
    return _DocMarkdownConverter(bullets='•', page_url=url).convert(html)


def _find_elements_until_tag(
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


_find_next_children_until_tag = partial(_find_elements_until_tag, func=partial(BeautifulSoup.find_all, recursive=False))
_find_next_siblings_until_tag = partial(_find_elements_until_tag, func=BeautifulSoup.find_next_siblings)
_find_previous_siblings_until_tag = partial(_find_elements_until_tag, func=BeautifulSoup.find_previous_siblings)


def get_module_description(start_element: PageElement) -> Optional[str]:
    """
    Get page content to a table or a tag with its class in `SEARCH_END_TAG_ATTRS`.

    A headerlink a tag is attempted to be found to skip repeating the module name in the description,
    if it's found it's used as the tag to search from instead of the `start_element`.
    """
    header = start_element.find("a", attrs={"class": "headerlink"})
    start_tag = header.parent if header is not None else start_element
    description = "".join(str(tag) for tag in _find_next_siblings_until_tag(start_tag, _match_end_tag))

    return description


def _get_symbol_description(symbol: PageElement) -> str:
    """Get the string contents of the next dd tag, up to a dt or a dl tag."""
    description_tag = symbol.find_next("dd")
    description_contents = _find_next_children_until_tag(description_tag, ("dt", "dl"))
    return "".join(str(tag) for tag in description_contents)


def _get_signatures(start_signature: PageElement) -> List[str]:
    """
    Collect up to 3 signatures from dt tags around the `start_signature` dt tag.

    First the signatures under the `start_signature` are included;
    if less than 2 are found, tags above the start signature are added to the result if any are present.
    """
    signatures = []
    for element in (
            *reversed(_find_previous_siblings_until_tag(start_signature, ("dd",), limit=2)),
            start_signature,
            *_find_next_siblings_until_tag(start_signature, ("dd",), limit=2),
    )[-3:]:
        signature = _UNWANTED_SIGNATURE_SYMBOLS_RE.sub("", element.text)

        if signature:
            signatures.append(signature)

    return signatures


def _truncate_markdown(markdown: str, max_length: int) -> str:
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


def _parse_into_markdown(signatures: Optional[List[str]], description: str, url: str) -> str:
    """
    Create a markdown string with the signatures at the top, and the converted html description below them.

    The signatures are wrapped in python codeblocks, separated from the description by a newline.
    The result string is truncated to be max 1000 symbols long.
    """
    description = _truncate_markdown(_markdownify(description, url=url), 1000)
    description = _WHITESPACE_AFTER_NEWLINES_RE.sub('', description)
    if signatures is not None:
        formatted_markdown = "".join(f"```py\n{textwrap.shorten(signature, 500)}```" for signature in signatures)
    else:
        formatted_markdown = ""
    formatted_markdown += f"\n{description}"

    return formatted_markdown


@async_cache(arg_offset=1)
async def _get_soup_from_url(http_session: ClientSession, url: str) -> BeautifulSoup:
    """Create a BeautifulSoup object from the HTML data in `url` with the head tag removed."""
    log.trace(f"Sending a request to {url}.")
    async with http_session.get(url) as response:
        soup = BeautifulSoup(await response.text(encoding="utf8"), 'lxml')
    soup.find("head").decompose()  # the head contains no useful data so we can remove it
    return soup


def _match_end_tag(tag: Tag) -> bool:
    """Matches `tag` if its class value is in `SEARCH_END_TAG_ATTRS` or the tag is table."""
    for attr in _SEARCH_END_TAG_ATTRS:
        if attr in tag.get("class", ()):
            return True

    return tag.name == "table"


async def get_symbol_markdown(http_session: ClientSession, symbol_data: "DocItem") -> str:
    """
    Return parsed markdown of the passed symbol, truncated to 1000 characters.

    A request through `http_session` is made to the url associated with `symbol_data` for the html contents;
    the contents are then parsed depending on what group the symbol belongs to.
    """
    if "#" in symbol_data.url:
        request_url, symbol_id = symbol_data.url.rsplit('#')
    else:
        request_url = symbol_data.url
        symbol_id = None

    soup = await _get_soup_from_url(http_session, request_url)
    symbol_heading = soup.find(id=symbol_id)

    # Handle doc symbols as modules, because they either link to the page of a module,
    # or don't contain any useful info to be parsed.
    signature = None
    if symbol_data.group in {"module", "doc"}:
        description = get_module_description(symbol_heading)

    elif symbol_data.group in _NO_SIGNATURE_GROUPS:
        description = _get_symbol_description(symbol_heading)

    else:
        signature = _get_signatures(symbol_heading)
        description = _get_symbol_description(symbol_heading)

    return _parse_into_markdown(signature, description.replace('¶', ''), symbol_data.url)
