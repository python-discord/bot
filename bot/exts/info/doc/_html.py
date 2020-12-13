import logging
from typing import List, Union

from bs4.element import PageElement, SoupStrainer

log = logging.getLogger(__name__)


class Strainer(SoupStrainer):
    """Subclass of SoupStrainer to allow matching of both `Tag`s and `NavigableString`s."""

    def __init__(self, *, include_strings: bool, **kwargs):
        self.include_strings = include_strings
        passed_text = kwargs.pop("text", None)
        if passed_text is not None:
            log.warning("`text` is not a supported kwarg in the custom strainer.")
        super().__init__(**kwargs)

    markup_hint = Union[PageElement, List["markup_hint"]]

    def search(self, markup: markup_hint) -> Union[PageElement, str]:
        """Extend default SoupStrainer behaviour to allow matching both `Tag`s` and `NavigableString`s."""
        if isinstance(markup, str):
            # Let everything through the text filter if we're including strings and tags.
            if not self.name and not self.attrs and self.include_strings:
                return markup
        else:
            return super().search(markup)
