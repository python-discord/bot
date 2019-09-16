import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse


def test_stars_valid():
    """Validates that `bot/resources/stars.json` contains valid images."""

    path = Path('bot', 'resources', 'stars.json')
    content = path.read_text()
    data = json.loads(content)

    for url in data.values():
        assert urlparse(url).scheme == 'https'

        mimetype, _ = mimetypes.guess_type(url)
        assert mimetype in ('image/jpeg', 'image/png')
