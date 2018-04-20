# coding=utf-8
import logging
import os
from collections import ChainMap
from pathlib import Path

import yaml


log = logging.getLogger(__name__)


with open('config-example.yml') as f:
    _CONFIG_YAML = ChainMap(yaml.safe_load(f))


if Path('config.yml').exists():
    log.debug("Found `config.yml` file, loading constants from it.")
    with open('config.yml') as f:
        _CONFIG_YAML = _CONFIG_YAML.new_child(yaml.safe_load(f))


_BOT_CONFIG = _CONFIG_YAML['bot']
_CLICKUP_CONFIG = _CONFIG_YAML['clickup']
_GUILD_CONFIG = _CONFIG_YAML['guild']
_CHANNELS_CONFIG = _GUILD_CONFIG['channels']
_ROLES_CONFIG = _GUILD_CONFIG['roles']


# Channels, servers and roles
PYTHON_GUILD = _GUILD_CONFIG['id']

BOT_CHANNEL = _GUILD_CONFIG['channels']['bot']
HELP1_CHANNEL = _CHANNELS_CONFIG['help1']
HELP2_CHANNEL = _CHANNELS_CONFIG['help2']
HELP3_CHANNEL = _CHANNELS_CONFIG['help3']
PYTHON_CHANNEL = _CHANNELS_CONFIG['python']
DEVLOG_CHANNEL = _CHANNELS_CONFIG['devlog']
DEVTEST_CHANNEL = _CHANNELS_CONFIG['devtest']
VERIFICATION_CHANNEL = _CHANNELS_CONFIG['verification']
CHECKPOINT_TEST_CHANNEL = _CHANNELS_CONFIG['checkpoint_test']

ADMIN_ROLE = _ROLES_CONFIG['admin']
MODERATOR_ROLE = _ROLES_CONFIG['moderator']
VERIFIED_ROLE = _ROLES_CONFIG['verified']
OWNER_ROLE = _ROLES_CONFIG['owner']
DEVOPS_ROLE = _ROLES_CONFIG['devops']
CONTRIBUTOR_ROLE = _ROLES_CONFIG['contributor']

# Clickup
CLICKUP_KEY = os.environ.get("CLICKUP_KEY")
CLICKUP_SPACE = _CONFIG_YAML['clickup']['space']
CLICKUP_TEAM = _CONFIG_YAML['clickup']['team']

# URLs
DEPLOY_URL = os.environ.get("DEPLOY_URL")
STATUS_URL = os.environ.get("STATUS_URL")
SITE_URL = os.environ.get("SITE_URL", "pythondiscord.local:8080")
SITE_PROTOCOL = 'http' if 'local' in SITE_URL else 'https'
SITE_API_USER_URL = f"{SITE_PROTOCOL}://api.{SITE_URL}/user"
SITE_API_TAGS_URL = f"{SITE_PROTOCOL}://api.{SITE_URL}/tags"
GITHUB_URL_BOT = _CONFIG_YAML['urls']['github_bot_repo']
BOT_AVATAR_URL = _CONFIG_YAML['urls']['bot_avatar']

# Keys
DEPLOY_BOT_KEY = os.environ.get("DEPLOY_BOT_KEY")
DEPLOY_SITE_KEY = os.environ.get("DEPLOY_SITE_KEY")
SITE_API_KEY = os.environ.get("BOT_API_KEY")

# Bot internals
HELP_PREFIX = _BOT_CONFIG['help_prefix']
TAG_COOLDOWN = _BOT_CONFIG['cooldowns']['tags']

# There are Emoji objects, but they're not usable until the bot is connected,
# so we're using string constants instead
GREEN_CHEVRON = _BOT_CONFIG['emojis']['green_chevron']
RED_CHEVRON = _BOT_CONFIG['emojis']['red_chevron']
WHITE_CHEVRON = _BOT_CONFIG['emojis']['white_chevron']

# PaperTrail logging
PAPERTRAIL_ADDRESS = os.environ.get("PAPERTRAIL_ADDRESS") or None
PAPERTRAIL_PORT = int(os.environ.get("PAPERTRAIL_PORT") or 0)
