# coding=utf-8
import logging
import os
from collections import ChainMap
from pathlib import Path

import yaml


log = logging.getLogger(__name__)


def _required_env_var_constructor(loader, node):
    value = loader.construct_scalar(node)
    return os.environ[value]


def _env_var_constructor(loader, node):
    value = loader.construct_scalar(node)
    return os.getenv(value)


yaml.SafeLoader.add_constructor('!REQUIRED_ENV', _required_env_var_constructor)
yaml.SafeLoader.add_constructor('!ENV', _env_var_constructor)


with open('config-example.yml') as f:
    _CONFIG_YAML = ChainMap(yaml.safe_load(f))


if Path('config.yml').exists():
    log.error("Found `config.yml` file, loading constants from it.")
    with open('config.yml') as f:
        _CONFIG_YAML.new_child(yaml.safe_load(f))


_BOT_CONFIG = _CONFIG_YAML['bot']
_CLICKUP_CONFIG = _CONFIG_YAML['clickup']
_GUILD_CONFIG = _CONFIG_YAML['guild']
_CHANNELS_CONFIG = _GUILD_CONFIG['channels']
_KEYS_CONFIG = _CONFIG_YAML['keys']
_ROLES_CONFIG = _GUILD_CONFIG['roles']
_URLS_CONFIG = _CONFIG_YAML['urls']


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
DEPLOY_URL = _URLS_CONFIG['deploy']
STATUS_URL = _URLS_CONFIG['status']
SITE_URL = _URLS_CONFIG['site'] or "pythondiscord.local:8080"
SITE_PROTOCOL = 'http' if 'local' in SITE_URL else 'https'
SITE_API_USER_URL = f"{SITE_PROTOCOL}://api.{SITE_URL}/user"
SITE_API_TAGS_URL = f"{SITE_PROTOCOL}://api.{SITE_URL}/tags"
GITHUB_URL_BOT = _URLS_CONFIG['github_bot_repo']
BOT_AVATAR_URL = _URLS_CONFIG['bot_avatar']

# Keys
DEPLOY_BOT_KEY = _KEYS_CONFIG['deploy_bot']
DEPLOY_SITE_KEY = _KEYS_CONFIG['deploy_site']
SITE_API_KEY = _KEYS_CONFIG['site_api']

# Bot internals
HELP_PREFIX = _BOT_CONFIG['help_prefix']
TAG_COOLDOWN = _BOT_CONFIG['cooldowns']['tags']

# There are Emoji objects, but they're not usable until the bot is connected,
# so we're using string constants instead
GREEN_CHEVRON = _BOT_CONFIG['emojis']['green_chevron']
RED_CHEVRON = _BOT_CONFIG['emojis']['red_chevron']
WHITE_CHEVRON = _BOT_CONFIG['emojis']['white_chevron']

# PaperTrail logging
PAPERTRAIL_ADDRESS = _CONFIG_YAML['papertrail']['address']
PAPERTRAIL_PORT = int(_CONFIG_YAML['papertrail']['port'] or 0)
