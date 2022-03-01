import tldextract

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter


class DomainFilter(Filter):
    """A filter which looks for a specific domain given by URL."""

    def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a domain within a given context."""
        domain = tldextract.extract(self.content).registered_domain

        for found_url in ctx.content:
            if self.content in found_url and tldextract.extract(found_url).registered_domain == domain:
                ctx.matches.append(self.content)
                if (
                        ("delete_messages" in self.actions and self.actions.get("delete_messages").delete_messages)
                        or not ctx.notification_domain
                ):  # Override this field only if this filter causes deletion.
                    ctx.notification_domain = self.content
                return True
        return False
