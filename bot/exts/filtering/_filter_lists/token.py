from __future__ import annotations

import re
import typing

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._filters.token import TokenFilter
from bot.exts.filtering._utils import clean_input

if typing.TYPE_CHECKING:
    from bot.exts.filtering.filtering import Filtering

SPOILER_RE = re.compile(r"(\|\|.+?\|\|)", re.DOTALL)


class TokensList(FilterList):
    """A list of filters, each looking for a specific token given by regex."""

    name = "token"

    def __init__(self, filtering_cog: Filtering):
        super().__init__(TokenFilter)
        filtering_cog.subscribe(self, Event.MESSAGE, Event.MESSAGE_EDIT)

    def triggers_for(self, ctx: FilterContext) -> list[Filter]:
        """Dispatch the given event to the list's filters, and return filters triggered."""
        text = ctx.content
        if SPOILER_RE.search(text):
            text = self._expand_spoilers(text)
        text = clean_input(text)
        ctx = ctx.replace(content=text)

        return self.filter_list_result(
            ctx, self._filter_lists[ListType.DENY], self._defaults[ListType.DENY]["validations"]
        )

    @staticmethod
    def _expand_spoilers(text: str) -> str:
        """Return a string containing all interpretations of a spoilered message."""
        split_text = SPOILER_RE.split(text)
        return ''.join(
            split_text[0::2] + split_text[1::2] + split_text
        )
