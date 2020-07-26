from urllib.parse import urljoin

from bs4.element import PageElement
from markdownify import MarkdownConverter


class _DocMarkdownConverter(MarkdownConverter):
    """Subclass markdownify's MarkdownCoverter to provide custom conversion methods."""

    def __init__(self, *, page_url: str, **options):
        super().__init__(**options)
        self.page_url = page_url

    def convert_li(self, el: PageElement, text: str) -> str:
        """Fix markdownify's erroneous indexing in ol tags."""
        parent = el.parent
        if parent is not None and parent.name == 'ol':
            li_tags = parent.find_all("li")
            bullet = '%s.' % (li_tags.index(el)+1)
        else:
            depth = -1
            while el:
                if el.name == 'ul':
                    depth += 1
                el = el.parent
            bullets = self.options['bullets']
            bullet = bullets[depth % len(bullets)]
        return '%s %s\n' % (bullet, text or '')

    def convert_hn(self, _n: int, el: PageElement, text: str) -> str:
        """Convert h tags to bold text with ** instead of adding #."""
        return f"**{text}**\n\n"

    def convert_code(self, el: PageElement, text: str) -> str:
        """Undo `markdownify`s underscore escaping."""
        return f"`{text}`".replace('\\', '')

    def convert_pre(self, el: PageElement, text: str) -> str:
        """Wrap any codeblocks in `py` for syntax highlighting."""
        code = ''.join(el.strings)
        return f"```py\n{code}```"

    def convert_a(self, el: PageElement, text: str) -> str:
        """Resolve relative URLs to `self.page_url`."""
        el["href"] = urljoin(self.page_url, el["href"])
        return super().convert_a(el, text)

    def convert_p(self, el: PageElement, text: str) -> str:
        """Include only one newline instead of two when the parent is a li tag."""
        parent = el.parent
        if parent is not None and parent.name == "li":
            return f"{text}\n"
        return super().convert_p(el, text)


def markdownify(html: str, *, url: str = "") -> str:
    """Create a DocMarkdownConverter object from the input html."""
    return _DocMarkdownConverter(bullets='•', page_url=url).convert(html)
