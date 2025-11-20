import re
from typing import Literal

from bot.constants import Channels, Roles

ANSI_REGEX = re.compile(r"\N{ESC}\[[0-9;:]*m")
ESCAPE_REGEX = re.compile("[`\u202E\u200B]{3,}")

# Max to display in a codeblock before sending to a paste service
# This also applies to text files
MAX_OUTPUT_BLOCK_LINES = 10
MAX_OUTPUT_BLOCK_CHARS = 1000

# The Snekbox commands' whitelists and blacklists.
NO_SNEKBOX_CHANNELS = (Channels.python_general,)
NO_SNEKBOX_CATEGORIES = ()
SNEKBOX_ROLES = (Roles.helpers, Roles.moderators, Roles.admins, Roles.owners, Roles.python_community)

REDO_EMOJI = "\U0001f501"  # :repeat:
REDO_TIMEOUT = 30

SupportedPythonVersions = Literal["3.13", "3.14", "3.14t", "3.14j"]

DEFAULT_PYTHON_VERSION: SupportedPythonVersions = "3.14"
