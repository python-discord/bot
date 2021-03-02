"""
Loads bot configuration from YAML files.
By default, this simply loads the default
configuration located at `config-default.yml`.
If a file called `config.yml` is found in the
project directory, the default configuration
is recursively updated with any settings from
the custom configuration. Any settings left
out in the custom user configuration will stay
their default values from `config-default.yml`.
"""

import logging
import os
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import yaml

log = logging.getLogger(__name__)


def _env_var_constructor(loader, node):
    """
    Implements a custom YAML tag for loading optional environment
    variables. If the environment variable is set, returns the
    value of it. Otherwise, returns `None`.

    Example usage in the YAML configuration:

        # Optional app configuration. Set `MY_APP_KEY` in the environment to use it.
        application:
            key: !ENV 'MY_APP_KEY'
    """

    default = None

    # Check if the node is a plain string value
    if node.id == 'scalar':
        value = loader.construct_scalar(node)
        key = str(value)
    else:
        # The node value is a list
        value = loader.construct_sequence(node)

        if len(value) >= 2:
            # If we have at least two values, then we have both a key and a default value
            default = value[1]
            key = value[0]
        else:
            # Otherwise, we just have a key
            key = value[0]

    return os.getenv(key, default)


def _join_var_constructor(loader, node):
    """
    Implements a custom YAML tag for concatenating other tags in
    the document to strings. This allows for a much more DRY configuration
    file.
    """

    fields = loader.construct_sequence(node)
    return "".join(str(x) for x in fields)


yaml.SafeLoader.add_constructor("!ENV", _env_var_constructor)
yaml.SafeLoader.add_constructor("!JOIN", _join_var_constructor)

# Pointing old tag to !ENV constructor to avoid breaking existing configs
yaml.SafeLoader.add_constructor("!REQUIRED_ENV", _env_var_constructor)


with open("config-default.yml", encoding="UTF-8") as f:
    _CONFIG_YAML = yaml.safe_load(f)


def _recursive_update(original, new):
    """
    Helper method which implements a recursive `dict.update`
    method, used for updating the original configuration with
    configuration specified by the user.
    """

    for key, value in original.items():
        if key not in new:
            continue

        if isinstance(value, Mapping):
            if not any(isinstance(subvalue, Mapping) for subvalue in value.values()):
                original[key].update(new[key])
            _recursive_update(original[key], new[key])
        else:
            original[key] = new[key]


if Path("config.yml").exists():
    log.info("Found `config.yml` file, loading constants from it.")
    with open("config.yml", encoding="UTF-8") as f:
        user_config = yaml.safe_load(f)
    _recursive_update(_CONFIG_YAML, user_config)


def check_required_keys(keys):
    """
    Verifies that keys that are set to be required are present in the
    loaded configuration.
    """
    for key_path in keys:
        lookup = _CONFIG_YAML
        try:
            for key in key_path.split('.'):
                lookup = lookup[key]
                if lookup is None:
                    raise KeyError(key)
        except KeyError:
            log.critical(
                f"A configuration for `{key_path}` is required, but was not found. "
                "Please set it in `config.yml` or setup an environment variable and try again."
            )
            raise


try:
    required_keys = _CONFIG_YAML['config']['required_keys']
except KeyError:
    pass
else:
    check_required_keys(required_keys)


class YAMLGetter(type):
    """
    Implements a custom metaclass used for accessing
    configuration data by simply accessing class attributes.
    Supports getting configuration from up to two levels
    of nested configuration through `section` and `subsection`.

    `section` specifies the YAML configuration section (or "key")
    in which the configuration lives, and must be set.

    `subsection` is an optional attribute specifying the section
    within the section from which configuration should be loaded.

    Example Usage:

        # config.yml
        bot:
            prefixes:
                direct_message: ''
                guild: '!'

        # config.py
        class Prefixes(metaclass=YAMLGetter):
            section = "bot"
            subsection = "prefixes"

        # Usage in Python code
        from config import Prefixes
        def get_prefix(bot, message):
            if isinstance(message.channel, PrivateChannel):
                return Prefixes.direct_message
            return Prefixes.guild
    """

    subsection = None

    def __getattr__(cls, name):
        name = name.lower()

        try:
            if cls.subsection is not None:
                return _CONFIG_YAML[cls.section][cls.subsection][name]
            return _CONFIG_YAML[cls.section][name]
        except KeyError:
            dotted_path = '.'.join(
                (cls.section, cls.subsection, name)
                if cls.subsection is not None else (cls.section, name)
            )
            log.critical(f"Tried accessing configuration variable at `{dotted_path}`, but it could not be found.")
            raise

    def __getitem__(cls, name):
        return cls.__getattr__(name)

    def __iter__(cls):
        """Return generator of key: value pairs of current constants class' config values."""
        for name in cls.__annotations__:
            yield name, getattr(cls, name)


# Dataclasses
class Bot(metaclass=YAMLGetter):
    section = "bot"

    prefix: str
    sentry_dsn: Optional[str]
    token: str


class Redis(metaclass=YAMLGetter):
    section = "bot"
    subsection = "redis"

    host: str
    password: Optional[str]
    port: int
    use_fakeredis: bool  # If this is True, Bot will use fakeredis.aioredis


class Filter(metaclass=YAMLGetter):
    section = "filter"

    filter_domains: bool
    filter_everyone_ping: bool
    filter_invites: bool
    filter_zalgo: bool
    watch_regex: bool
    watch_rich_embeds: bool

    # Notifications are not expected for "watchlist" type filters

    notify_user_domains: bool
    notify_user_everyone_ping: bool
    notify_user_invites: bool
    notify_user_zalgo: bool

    offensive_msg_delete_days: int
    ping_everyone: bool

    channel_whitelist: List[int]
    role_whitelist: List[int]


class Cooldowns(metaclass=YAMLGetter):
    section = "bot"
    subsection = "cooldowns"

    tags: int


class Colours(metaclass=YAMLGetter):
    section = "style"
    subsection = "colours"

    blue: int
    bright_green: int
    orange: int
    pink: int
    purple: int
    soft_green: int
    soft_orange: int
    soft_red: int
    white: int
    yellow: int


class DuckPond(metaclass=YAMLGetter):
    section = "duck_pond"

    threshold: int
    channel_blacklist: List[int]


class Emojis(metaclass=YAMLGetter):
    section = "style"
    subsection = "emojis"

    badge_bug_hunter: str
    badge_bug_hunter_level_2: str
    badge_early_supporter: str
    badge_hypesquad: str
    badge_hypesquad_balance: str
    badge_hypesquad_bravery: str
    badge_hypesquad_brilliance: str
    badge_partner: str
    badge_staff: str
    badge_verified_bot_developer: str

    defcon_shutdown: str  # noqa: E704
    defcon_unshutdown: str  # noqa: E704
    defcon_update: str  # noqa: E704

    failmail: str

    incident_actioned: str
    incident_investigating: str
    incident_unactioned: str

    status_dnd: str
    status_idle: str
    status_offline: str
    status_online: str

    trashcan: str

    bullet: str
    check_mark: str
    cross_mark: str
    new: str
    pencil: str

    comments: str
    upvotes: str
    user: str

    ok_hand: str


class Icons(metaclass=YAMLGetter):
    section = "style"
    subsection = "icons"

    crown_blurple: str
    crown_green: str
    crown_red: str

    defcon_denied: str    # noqa: E704
    defcon_shutdown: str  # noqa: E704
    defcon_unshutdown: str   # noqa: E704
    defcon_update: str   # noqa: E704

    filtering: str

    green_checkmark: str
    green_questionmark: str
    guild_update: str

    hash_blurple: str
    hash_green: str
    hash_red: str

    message_bulk_delete: str
    message_delete: str
    message_edit: str

    pencil: str

    questionmark: str

    remind_blurple: str
    remind_green: str
    remind_red: str

    sign_in: str
    sign_out: str

    superstarify: str
    unsuperstarify: str

    token_removed: str

    user_ban: str
    user_mute: str
    user_unban: str
    user_unmute: str
    user_update: str
    user_verified: str
    user_warn: str

    voice_state_blue: str
    voice_state_green: str
    voice_state_red: str


class CleanMessages(metaclass=YAMLGetter):
    section = "bot"
    subsection = "clean"

    message_limit: int


class Stats(metaclass=YAMLGetter):
    section = "bot"
    subsection = "stats"

    presence_update_timeout: int
    statsd_host: str


class Categories(metaclass=YAMLGetter):
    section = "guild"
    subsection = "categories"

    help_available: int
    help_dormant: int
    help_in_use: int
    modmail: int
    voice: int


class Channels(metaclass=YAMLGetter):
    section = "guild"
    subsection = "channels"

    announcements: int
    change_log: int
    mailing_lists: int
    python_events: int
    python_news: int
    reddit: int
    user_event_announcements: int

    dev_contrib: int
    dev_core: int
    dev_log: int

    meta: int
    python_general: int

    cooldown: int

    attachment_log: int
    dm_log: int
    message_log: int
    mod_log: int
    user_log: int
    voice_log: int

    off_topic_0: int
    off_topic_1: int
    off_topic_2: int

    bot_commands: int
    discord_py: int
    esoteric: int
    voice_gate: int

    admins: int
    admin_spam: int
    defcon: int
    helpers: int
    incidents: int
    incidents_archive: int
    mods: int
    mod_alerts: int
    mod_spam: int
    organisation: int

    admin_announcements: int
    mod_announcements: int
    staff_announcements: int

    admins_voice: int
    code_help_voice_1: int
    code_help_voice_2: int
    general_voice: int
    staff_voice: int

    code_help_chat_1: int
    code_help_chat_2: int
    staff_voice_chat: int
    voice_chat: int

    big_brother_logs: int
    talent_pool: int


class Webhooks(metaclass=YAMLGetter):
    section = "guild"
    subsection = "webhooks"

    big_brother: int
    dev_log: int
    dm_log: int
    duck_pond: int
    incidents_archive: int
    reddit: int
    talent_pool: int


class Roles(metaclass=YAMLGetter):
    section = "guild"
    subsection = "roles"

    announcements: int
    contributors: int
    help_cooldown: int
    muted: int
    partners: int
    python_community: int
    sprinters: int
    voice_verified: int

    admins: int
    core_developers: int
    devops: int
    helpers: int
    moderators: int
    owners: int

    jammers: int
    team_leaders: int


class Guild(metaclass=YAMLGetter):
    section = "guild"

    id: int
    invite: str  # Discord invite, gets embedded in chat

    moderation_categories: List[int]
    moderation_channels: List[int]
    modlog_blacklist: List[int]
    reminder_whitelist: List[int]
    moderation_roles: List[int]
    staff_roles: List[int]


class Keys(metaclass=YAMLGetter):
    section = "keys"

    github: Optional[str]
    site_api: Optional[str]


class URLs(metaclass=YAMLGetter):
    section = "urls"

    # Snekbox endpoints
    snekbox_eval_api: str

    # Discord API endpoints
    discord_api: str
    discord_invite_api: str

    # Misc endpoints
    bot_avatar: str
    github_bot_repo: str

    # Base site vars
    connect_max_retries: int
    connect_cooldown: int
    site: str
    site_api: str
    site_schema: str
    site_api_schema: str

    # Site endpoints
    site_logs_view: str
    paste_service: str


class Reddit(metaclass=YAMLGetter):
    section = "reddit"

    client_id: Optional[str]
    secret: Optional[str]
    subreddits: list


class AntiSpam(metaclass=YAMLGetter):
    section = 'anti_spam'

    clean_offending: bool
    ping_everyone: bool

    punishment: Dict[str, Dict[str, int]]
    rules: Dict[str, Dict[str, int]]


class BigBrother(metaclass=YAMLGetter):
    section = 'big_brother'

    header_message_limit: int
    log_delay: int


class CodeBlock(metaclass=YAMLGetter):
    section = 'code_block'

    channel_whitelist: List[int]
    cooldown_channels: List[int]
    cooldown_seconds: int
    minimum_lines: int


class Free(metaclass=YAMLGetter):
    section = 'free'

    activity_timeout: int
    cooldown_per: float
    cooldown_rate: int


class HelpChannels(metaclass=YAMLGetter):
    section = 'help_channels'

    enable: bool
    claim_minutes: int
    cmd_whitelist: List[int]
    idle_minutes: int
    deleted_idle_minutes: int
    max_available: int
    max_total_channels: int
    name_prefix: str
    notify: bool
    notify_channel: int
    notify_minutes: int
    notify_roles: List[int]


class RedirectOutput(metaclass=YAMLGetter):
    section = 'redirect_output'

    delete_delay: int
    delete_invocation: bool


class PythonNews(metaclass=YAMLGetter):
    section = 'python_news'

    channel: int
    webhook: int
    mail_lists: List[str]


class VoiceGate(metaclass=YAMLGetter):
    section = "voice_gate"

    bot_message_delete_delay: int
    minimum_activity_blocks: int
    minimum_days_member: int
    minimum_messages: int
    voice_ping_delete_delay: int


class Branding(metaclass=YAMLGetter):
    section = "branding"

    cycle_frequency: int


class Event(Enum):
    """
    Event names. This does not include every event (for example, raw
    events aren't here), but only events used in ModLog for now.
    """

    guild_channel_create = "guild_channel_create"
    guild_channel_delete = "guild_channel_delete"
    guild_channel_update = "guild_channel_update"
    guild_role_create = "guild_role_create"
    guild_role_delete = "guild_role_delete"
    guild_role_update = "guild_role_update"
    guild_update = "guild_update"

    member_join = "member_join"
    member_remove = "member_remove"
    member_ban = "member_ban"
    member_unban = "member_unban"
    member_update = "member_update"

    message_delete = "message_delete"
    message_edit = "message_edit"

    voice_state_update = "voice_state_update"


# Debug mode
DEBUG_MODE = 'local' in os.environ.get("SITE_URL", "local")

# Paths
BOT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BOT_DIR, os.pardir))

# Default role combinations
MODERATION_ROLES = Guild.moderation_roles
STAFF_ROLES = Guild.staff_roles

# Channel combinations
MODERATION_CHANNELS = Guild.moderation_channels

# Category combinations
MODERATION_CATEGORIES = Guild.moderation_categories

# Git SHA for Sentry
GIT_SHA = os.environ.get("GIT_SHA", "development")

# Bot replies
NEGATIVE_REPLIES = [
    "Noooooo!!",
    "Nope.",
    "I'm sorry Dave, I'm afraid I can't do that.",
    "I don't think so.",
    "Not gonna happen.",
    "Out of the question.",
    "Huh? No.",
    "Nah.",
    "Naw.",
    "Not likely.",
    "No way, José.",
    "Not in a million years.",
    "Fat chance.",
    "Certainly not.",
    "NEGATORY.",
    "Nuh-uh.",
    "Not in my house!",
]

POSITIVE_REPLIES = [
    "Yep.",
    "Absolutely!",
    "Can do!",
    "Affirmative!",
    "Yeah okay.",
    "Sure.",
    "Sure thing!",
    "You're the boss!",
    "Okay.",
    "No problem.",
    "I got you.",
    "Alright.",
    "You got it!",
    "ROGER THAT",
    "Of course!",
    "Aye aye, cap'n!",
    "I'll allow it.",
]

ERROR_REPLIES = [
    "Please don't do that.",
    "You have to stop.",
    "Do you mind?",
    "In the future, don't do that.",
    "That was a mistake.",
    "You blew it.",
    "You're bad at computers.",
    "Are you trying to kill me?",
    "Noooooo!!",
    "I can't believe you've done this",
]
