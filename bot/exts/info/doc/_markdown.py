import re
from urllib.parse import urljoin

import markdownify
from bs4.element import PageElement

# See https://github.com/matthewwithanm/python-markdownify/issues/31
markdownify.whitespace_re = re.compile(r"[\r\n\s\t ]+")


class DocMarkdownConverter(markdownify.MarkdownConverter):
    """Subclass markdownify's MarkdownCoverter to provide custom conversion methods."""

    def __init__(self, *, page_url: str, **options):
        super().__init__(**options)
        self.page_url = page_url

    def convert_li(self, el: PageElement, text: str, convert_as_inline: bool) -> str:
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

    def convert_hn(self, _n: int, el: PageElement, text: str, convert_as_inline: bool) -> str:
        """Convert h tags to bold text with ** instead of adding #."""
        if convert_as_inline:
            return text
        return f"**{text}**\n\n"

    def convert_code(self, el: PageElement, text: str, convert_as_inline: bool) -> str:
        """Undo `markdownify`s underscore escaping."""
        return f"`{text}`".replace("\\", "")

    def convert_pre(self, el: PageElement, text: str, convert_as_inline: bool) -> str:
        """Wrap any codeblocks in `py` for syntax highlighting."""
        code = "".join(el.strings)
        return f"```py\n{code}```"

    def convert_a(self, el: PageElement, text: str, convert_as_inline: bool) -> str:
        """Resolve relative URLs to `self.page_url`."""
        el["href"] = urljoin(self.page_url, el["href"])
        # Discord doesn't handle titles properly, showing links with them as raw text.
        el["title"] = None
        return super().convert_a(el, text, convert_as_inline)

    def convert_p(self, el: PageElement, text: str, convert_as_inline: bool) -> str:
        """Include only one newline instead of two when the parent is a li tag."""
        if convert_as_inline:
            return text

        parent = el.parent
        if parent is not None and parent.name == "li":
            return f"{text}\n"
        return super().convert_p(el, text, convert_as_inline)

    def convert_hr(self, el: PageElement, text: str, convert_as_inline: bool) -> str:
        """Ignore `hr` tag."""
        return ""
