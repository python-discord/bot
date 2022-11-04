from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter


class ExtensionFilter(Filter):
    """
    A filter which looks for a specific attachment extension in messages.

    The filter stores the extension preceded by a dot.
    """

    name = "extension"

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for an attachment extension in the context content, given as a set of extensions."""
        return self.content in ctx.content

    @classmethod
    async def process_input(cls, content: str, description: str) -> tuple[str, str]:
        """
        Process the content and description into a form which will work with the filtering.

        A BadArgument should be raised if the content can't be used.
        """
        if not content.startswith("."):
            content = f".{content}"
        return content, description
