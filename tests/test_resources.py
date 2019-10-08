import json
from pathlib import Path


def test_stars_valid():
    """Validates that `bot/resources/stars.json` contains a list of strings."""

    path = Path('bot', 'resources', 'stars.json')
    content = path.read_text()
    data = json.loads(content)

    for name in data:
        assert type(name) is str
