from collections.abc import Callable, Container, Iterable
from functools import partial

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PageElement, SoupStrainer, Tag

from bot.log import get_logger

from . import MAX_SIGNATURE_AMOUNT

log = get_logger(__name__)

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


class Strainer(SoupStrainer):
    """Subclass of SoupStrainer to allow matching of both `Tag`s and `NavigableString`s."""

    def __init__(self, *, include_strings: bool, **kwargs):
        self.include_strings = include_strings
        passed_text = kwargs.pop("text", None)
        if passed_text is not None:
            log.warning("`text` is not a supported kwarg in the custom strainer.")
        super().__init__(**kwargs)

    Markup = PageElement | list["Markup"]

    def search(self, markup: Markup) -> PageElement | str:
        """Extend default SoupStrainer behaviour to allow matching both `Tag`s` and `NavigableString`s."""
        if isinstance(markup, str):
            # Let everything through the text filter if we're including strings and tags.
            if not self.name and not self.attrs and self.include_strings:
                return markup
            return None
        return super().search(markup)


def _find_elements_until_tag(
    start_element: PageElement,
    end_tag_filter: Container[str] | Callable[[Tag], bool],
    *,
    func: Callable,
    include_strings: bool = False,
    limit: int | None = None,
) -> list[Tag | NavigableString]:
    """
    Get all elements up to `limit` or until a tag matching `end_tag_filter` is found.

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


def _class_filter_factory(class_names: Iterable[str]) -> Callable[[Tag], bool]:
    """Create callable that returns True when the passed in tag's class is in `class_names` or when it's a table."""
    def match_tag(tag: Tag) -> bool:
        for attr in class_names:
            if attr in tag.get("class", ()):
                return True
        return tag.name == "table"

    return match_tag


def get_general_description(start_element: Tag) -> list[Tag | NavigableString]:
    """
    Get page content to a table or a tag with its class in `SEARCH_END_TAG_ATTRS`.

    A headerlink tag is attempted to be found to skip repeating the symbol information in the description.
    If it's found it's used as the tag to start the search from instead of the `start_element`.
    """
    child_tags = _find_recursive_children_until_tag(start_element, _class_filter_factory(["section"]), limit=100)
    header = next(filter(_class_filter_factory(["headerlink"]), child_tags), None)
    start_tag = header.parent if header is not None else start_element
    return _find_next_siblings_until_tag(start_tag, _class_filter_factory(_SEARCH_END_TAG_ATTRS), include_strings=True)


def get_dd_description(symbol: PageElement) -> list[Tag | NavigableString]:
    """Get the contents of the next dd tag, up to a dt or a dl tag."""
    description_tag = symbol.find_next("dd")
    return _find_next_children_until_tag(description_tag, ("dt", "dl"), include_strings=True)


def get_signatures(start_signature: PageElement) -> list[str]:
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
    )[-MAX_SIGNATURE_AMOUNT:]:
        for tag in element.find_all(_filter_signature_links, recursive=False):
            tag.decompose()

        signature = element.text
        if signature:
            signatures.append(signature)

    return signatures


def _filter_signature_links(tag: Tag) -> bool:
    """Return True if `tag` is a headerlink, or a link to source code; False otherwise."""
    if tag.name == "a":
        if "headerlink" in tag.get("class", ()):
            return True

        if tag.find(class_="viewcode-link"):
            return True

    return False
