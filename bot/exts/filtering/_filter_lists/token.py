from __future__ import annotations

import re
import typing
from functools import reduce
from operator import or_
from typing import Optional

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.token import TokenFilter
from bot.exts.filtering._settings import ActionSettings
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

    async def actions_for(self, ctx: FilterContext) -> tuple[Optional[ActionSettings], Optional[str]]:
        """Dispatch the given event to the list's filters, and return actions to take and a message to relay to mods."""
        text = ctx.content
        if not text:
            return None, ""
        if SPOILER_RE.search(text):
            text = self._expand_spoilers(text)
        text = clean_input(text)
        ctx = ctx.replace(content=text)

        triggers = self.filter_list_result(
            ctx, self.filter_lists[ListType.DENY], self.defaults[ListType.DENY]["validations"]
        )
        actions = None
        message = ""
        if triggers:
            actions = reduce(or_, (filter_.actions for filter_ in triggers))
            if len(triggers) == 1:
                message = f"#{triggers[0].id} (`{triggers[0].content}`)"
                if triggers[0].description:
                    message += f" - {triggers[0].description}"
            else:
                message = ", ".join(f"#{filter_.id} (`{filter_.content}`)" for filter_ in triggers)
        return actions, message

    @staticmethod
    def _expand_spoilers(text: str) -> str:
        """Return a string containing all interpretations of a spoilered message."""
        split_text = SPOILER_RE.split(text)
        return ''.join(
            split_text[0::2] + split_text[1::2] + split_text
        )
