from typing import NamedTuple


class DocItem(NamedTuple):
    """Holds inventory symbol information."""

    package: str
    """Name of the package name the symbol is from"""

    group: str
    """Interpshinx "role" of the symbol, for example `label` or `method`"""

    base_url: str
    """Absolute path to to which the relative path resolves, same for all items with the same package"""

    relative_url_path: str
    """Relative path to the page where the symbol is located"""

    symbol_id: str
    """Fragment id used to locate the symbol on the page"""

    @property
    def url(self) -> str:
        """Return the absolute url to the symbol."""
        return self.base_url + self.relative_url_path
