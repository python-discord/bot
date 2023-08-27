import re
from typing import ClassVar
from urllib.parse import urlparse

import tldextract
from discord.ext.commands import BadArgument
from pydantic import BaseModel

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter

URL_RE = re.compile(r"(?:https?://)?(\S+?)[\\/]*", flags=re.IGNORECASE)


class ExtraDomainSettings(BaseModel):
    """Extra settings for how domains should be matched in a message."""

    only_subdomains_description: ClassVar[str] = (
        "A boolean. If True, will only trigger for subdomains and subpaths, and not for the domain itself."
    )

    # Whether to trigger only for subdomains and subpaths, and not the specified domain itself.
    only_subdomains: bool = False


class DomainFilter(Filter):
    """
    A filter which looks for a specific domain given by URL.

    The schema (http, https) does not need to be included in the filter.
    Will also match subdomains.
    """

    name = "domain"
    extra_fields_type = ExtraDomainSettings

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a domain within a given context."""
        domain = tldextract.extract(self.content).registered_domain.lower()

        for found_url in ctx.content:
            extract = tldextract.extract(found_url)
            if self.content.lower() in found_url and extract.registered_domain == domain:
                if self.extra_fields.only_subdomains:
                    if not extract.subdomain and not urlparse(f"https://{found_url}").path:
                        return False
                ctx.matches.append(found_url)
                ctx.notification_domain = self.content
                return True
        return False

    @classmethod
    async def process_input(cls, content: str, description: str) -> tuple[str, str]:
        """
        Process the content and description into a form which will work with the filtering.

        A BadArgument should be raised if the content can't be used.
        """
        match = URL_RE.fullmatch(content)
        if not match or not match.group(1):
            raise BadArgument(f"`{content}` is not a URL.")
        return match.group(1), description
