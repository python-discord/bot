from collections.abc import Iterable
from typing import List, Union

from bs4.element import NavigableString, PageElement, SoupStrainer, Tag


class Strainer(SoupStrainer):
    """Subclass of SoupStrainer to allow matching of both `Tag`s and `NavigableString`s."""

    def __init__(self, *, include_strings: bool, **kwargs):
        self.include_strings = include_strings
        super().__init__(**kwargs)

    markup_hint = Union[PageElement, List["markup_hint"]]

    def search(self, markup: markup_hint) -> Union[PageElement, str]:
        """Extend default SoupStrainer behaviour to allow matching both `Tag`s` and `NavigableString`s."""
        if isinstance(markup, Iterable) and not isinstance(markup, (Tag, str)):
            for element in markup:
                if isinstance(element, NavigableString) and self.search(element):
                    return element
        elif isinstance(markup, Tag):
            # Also include tags while we're searching for strings and tags.
            if self.include_strings or (not self.text or self.name or self.attrs):
                return self.search_tag(markup)

        elif isinstance(markup, str):
            # Let everything through the text filter if we're including strings and tags.
            text_filter = None if not self.include_strings else True
            if not self.name and not self.attrs and self._matches(markup, text_filter):
                return markup
        else:
            raise Exception(f"I don't know how to match against a {markup.__class__}")
