import re

from bot.constants import Guild
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter

EVERYONE_PING_RE = re.compile(rf"@everyone|<@&{Guild.id}>|@here")
CODE_BLOCK_RE = re.compile(
    r"(?P<delim>``?)[^`]+?(?P=delim)(?!`+)"  # Inline codeblock
    r"|```(.+?)```",  # Multiline codeblock
    re.DOTALL | re.MULTILINE
)


class EveryoneFilter(UniqueFilter):
    """Filter messages which contain `@everyone` and `@here` tags outside a codeblock."""

    name = "everyone"
    events = (Event.MESSAGE, Event.MESSAGE_EDIT, Event.SNEKBOX)

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""
        # First pass to avoid running re.sub on every message
        if not EVERYONE_PING_RE.search(ctx.content):
            return False

        content_without_codeblocks = CODE_BLOCK_RE.sub("", ctx.content)
        return bool(EVERYONE_PING_RE.search(content_without_codeblocks))
