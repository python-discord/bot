from urllib.parse import urljoin

import markdownify
from bs4.element import PageElement


class DocMarkdownConverter(markdownify.MarkdownConverter):
    """Subclass markdownify's MarkdownCoverter to provide custom conversion methods."""

    def __init__(self, *, page_url: str, **options):
        # Reflow text to avoid unwanted line breaks.
        default_options = {"wrap": True, "wrap_width": None}

        super().__init__(**default_options | options)
        self.page_url = page_url

    def convert_li(self, el: PageElement, text: str, parent_tags: set[str]) -> str:
        """Fix markdownify's erroneous indexing in ol tags."""
        parent = el.parent
        if parent is not None and parent.name == "ol":
            li_tags = parent.find_all("li")
            bullet = f"{li_tags.index(el)+1}."
        else:
            depth = -1
            while el:
                if el.name == "ul":
                    depth += 1
                el = el.parent
            bullets = self.options["bullets"]
            bullet = bullets[depth % len(bullets)]
        return f"{bullet} {text}\n"

    def convert_hN(self, _n: int, el: PageElement, text: str, parent_tags: set[str]) -> str: # noqa: N802
        """Convert h tags to bold text with ** instead of adding #."""
        if "_inline" in parent_tags:
            return text
        return f"**{text}**\n\n"

    def convert_code(self, el: PageElement, text: str, parent_tags: set[str]) -> str:
        """Undo `markdownify`s underscore escaping."""
        return f"`{text}`".replace("\\", "")

    def convert_pre(self, el: PageElement, text: str, parent_tags: set[str]) -> str:
        """Wrap any codeblocks in `py` for syntax highlighting."""
        code = "".join(el.strings)
        return f"```py\n{code}```"

    def convert_a(self, el: PageElement, text: str, parent_tags: set[str]) -> str:
        """Resolve relative URLs to `self.page_url`."""
        el["href"] = urljoin(self.page_url, el["href"])
        # Discord doesn't handle titles properly, showing links with them as raw text.
        el["title"] = None
        return super().convert_a(el, text, parent_tags)

    def convert_p(self, el: PageElement, text: str, parent_tags: set[str]) -> str:
        """Include only one newline instead of two when the parent is a li tag."""
        if "_inline" in parent_tags:
            return text

        parent = el.parent
        if parent is not None and parent.name == "li":
            return f"{text}\n"
        return super().convert_p(el, text, parent_tags)

    def convert_hr(self, el: PageElement, text: str, parent_tags: set[str]) -> str:
        """Ignore `hr` tag."""
        return ""
