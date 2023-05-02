from __future__ import annotations

import re
import typing

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._filters.token import TokenFilter
from bot.exts.filtering._settings import ActionSettings
from bot.exts.filtering._utils import clean_input

if typing.TYPE_CHECKING:
    from bot.exts.filtering.filtering import Filtering

SPOILER_RE = re.compile(r"(\|\|.+?\|\|)", re.DOTALL)


class TokensList(FilterList[TokenFilter]):
    """
    A list of filters, each looking for a specific token in the given content given as regex.

    The blacklist defaults dictate what happens by default when a filter is matched, and can be overridden by
    individual filters.

    Usually, if blocking literal strings, the literals themselves can be specified as the filter's value.
    But since this is a list of regex patterns, be careful of the items added. For example, a dot needs to be escaped
    to function as a literal dot.
    """

    name = "token"

    def __init__(self, filtering_cog: Filtering):
        super().__init__()
        filtering_cog.subscribe(
            self, Event.MESSAGE, Event.MESSAGE_EDIT, Event.NICKNAME, Event.THREAD_NAME, Event.SNEKBOX
        )

    def get_filter_type(self, content: str) -> type[Filter]:
        """Get a subclass of filter matching the filter list and the filter's content."""
        return TokenFilter

    @property
    def filter_types(self) -> set[type[Filter]]:
        """Return the types of filters used by this list."""
        return {TokenFilter}

    async def actions_for(
        self, ctx: FilterContext
    ) -> tuple[ActionSettings | None, list[str], dict[ListType, list[Filter]]]:
        """Dispatch the given event to the list's filters, and return actions to take and messages to relay to mods."""
        text = ctx.content
        if not text:
            return None, [], {}
        if SPOILER_RE.search(text):
            text = self._expand_spoilers(text)
        text = clean_input(text)
        ctx = ctx.replace(content=text)

        triggers = await self[ListType.DENY].filter_list_result(ctx)
        actions = None
        messages = []
        if triggers:
            actions = self[ListType.DENY].merge_actions(triggers)
            messages = self[ListType.DENY].format_messages(triggers)
        return actions, messages, {ListType.DENY: triggers}

    @staticmethod
    def _expand_spoilers(text: str) -> str:
        """Return a string containing all interpretations of a spoilered message."""
        split_text = SPOILER_RE.split(text)
        return "".join(
            split_text[0::2] + split_text[1::2] + split_text
        )
