import re
from typing import ClassVar, Optional

import tldextract
from pydantic import BaseModel

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter

URL_RE = re.compile(r"(?:https?://)?(\S+?)[\\/]*", flags=re.IGNORECASE)


class ExtraDomainSettings(BaseModel):
    """Extra settings for how domains should be matched in a message."""

    exact_description: ClassVar[str] = (
        "A boolean. If True, will match the filter content exactly, and won't trigger for subdomains and subpaths."
    )

    # whether to match the filter content exactly, or to trigger for subdomains and subpaths as well.
    exact: Optional[bool] = False


class DomainFilter(Filter):
    """
    A filter which looks for a specific domain given by URL.

    The schema (http, https) does not need to be included in the filter.
    Will also match subdomains unless set otherwise.
    """

    name = "domain"
    extra_fields_type = ExtraDomainSettings

    def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a domain within a given context."""
        domain = tldextract.extract(self.content).registered_domain

        for found_url in ctx.content:
            if self.content in found_url and tldextract.extract(found_url).registered_domain == domain:
                ctx.matches.append(self.content)
                ctx.notification_domain = self.content
                return not self.extra_fields.exact or self.content == found_url
        return False

    @classmethod
    async def process_content(cls, content: str) -> str:
        """
        Process the content into a form which will work with the filtering.

        A ValueError should be raised if the content can't be used.
        """
        match = URL_RE.fullmatch(content)
        if not match or not match.group(1):
            raise ValueError(f"`{content}` is not a URL.")
        return match.group(1)
