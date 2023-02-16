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
from enum import Enum
from pathlib import Path
from pydantic import BaseSettings

# Will add a check for the required keys

env_file_path = Path(__file__).parent.parent / ".env"
server_env_file_path = Path(__file__).parent.parent / ".env.server"

# If env variables are not found in the previous files, fall back to the following
default_env_file_path = Path(__file__).parent.parent / ".env.default"
default_server_env_file_path = Path(__file__).parent.parent / ".env.server.default"


FILE_LOGS = True
DEBUG_MODE = True


class EnvConfig(BaseSettings):
    class Config:
        env_file = env_file_path, server_env_file_path, default_env_file_path, default_server_env_file_path
        env_file_encoding = 'utf-8'


class _Bot(EnvConfig):
    EnvConfig.Config.env_prefix = "bot__"

    prefix: str
    sentry_dsn: str | None
    token: str
    trace_loggers: str = "*"


Bot = _Bot()


class _Channels(EnvConfig):
    EnvConfig.Config.env_prefix = "channels__"
    announcements: int
    changelog: int
    mailing_lists: int
    python_events: int
    python_news: int
    reddit: int

    dev_contrib: int
    dev_core: int
    dev_log: int

    meta: int
    python_general: int

    help_system_forum: int

    attachment_log: int
    filter_log: int
    message_log: int
    mod_log: int
    nomination_archive: int
    user_log: int
    voice_log: int

    off_topic_0: int
    off_topic_1: int
    off_topic_2: int

    bot_commands: int
    discord_bots: int
    esoteric: int
    voice_gate: int
    code_jam_planning: int

    admins: int
    admin_spam: int
    defcon: int
    helpers: int
    incidents: int
    incidents_archive: int
    mod_alerts: int
    mod_meta: int
    mods: int
    nominations: int
    nomination_voting: int
    organisation: int

    admin_announcements: int
    mod_announcements: int
    staff_announcements: int
    staff_info: int

    admins_voice: int
    code_help_voice_0: int
    code_help_voice_1: int
    general_voice_0: int
    general_voice_1: int
    staff_voice: int

    code_help_chat_0: int
    code_help_chat_1: int
    staff_voice_chat: int
    voice_chat_0: int
    voice_chat_1: int

    big_brother_logs: int

    duck_pond: int


Channels = _Channels()


class _Roles(EnvConfig):

    EnvConfig.Config.env_prefix = "roles__"

    # Self-assignable roles, see the Subscribe cog
    advent_of_code: int
    advent_of_code: int
    announcements: int
    lovefest: int
    pyweek_announcements: int
    revival_of_code: int
    legacy_help_channels_access: int

    contributors: int
    help_cooldown: int
    muted: int
    partners: int
    python_community: int
    sprinters: int
    voice_verified: int
    video: int

    admins: int
    core_developers: int
    code_jam_event_team: int
    devops: int
    domain_leads: int
    events_lead: int
    helpers: int
    moderators: int
    mod_team: int
    owners: int
    project_leads: int

    jammers: int

    patreon_tier_1: int
    patreon_tier_2: int
    patreon_tier_3: int


Roles = _Roles()


class _Categories(EnvConfig):
    EnvConfig.Config.env_prefix = "categories__"

    moderators: int
    modmail: int
    voice: int

    # 2021 Summer Code Jam
    summer_code_jam: int


Categories = _Categories()


class _Guild(BaseSettings):
    EnvConfig.Config.env_prefix = "guild__"
    id: int
    invite: str
    roles: _Roles = Roles


Guild = _Guild()


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


class ThreadArchiveTimes(Enum):
    HOUR = 60
    DAY = 1440
    THREE_DAY = 4320
    WEEK = 10080


class _Webhooks(EnvConfig):

    big_brother: int
    dev_log: int
    duck_pond: int
    incidents: int
    incidents_archive: int
    python_news: int


Webhooks = _Webhooks()


class _BigBrother(EnvConfig):
    EnvConfig.Config.env_prefix = "big_brother__"

    header_message_limit: int
    log_delay: int


BigBrother = _BigBrother()


class _CodeBlock(EnvConfig):
    EnvConfig.Config.env_prefix = "code_block__"

    # The channels in which code blocks will be detected. They are not subject to a cooldown.
    channel_whitelist: int = Channels.bot_commands
    # The channels which will be affected by a cooldown. These channels are also whitelisted.
    cooldown_channels: int = Channels.python_general

    cooldown_seconds: int
    minimum_lines: int


CodeBlock = _CodeBlock()


class _Free(EnvConfig):
    EnvConfig.Config.env_prefix = "free__"

    activity_timeout: int
    cooldown_per: float
    cooldown_rate: int


Free = _Free()


class _HelpChannels(EnvConfig):
    EnvConfig.Config.env_prefix = 'help_channels__'

    enable: bool
    idle_minutes: int
    deleted_idle_minutes: int
    # Roles which are allowed to use the command which makes channels dormant
    cmd_whitelist: list[int] = [Roles.helpers]


HelpChannels = _HelpChannels()


class _RedirectOutput(EnvConfig):
    EnvConfig.Config.env_prefix = "redirect_output__"

    delete_delay: int
    delete_invocation: bool


RedirectOutput = _RedirectOutput()


class _DuckPond(EnvConfig):
    EnvConfig.Config.env_prefix = 'duck_pond__'

    channel_blacklist: list[str] = [
        Channels.announcements,
        Channels.python_news,
        Channels.python_events,
        Channels.mailing_lists,
        Channels.reddit,
        Channels.duck_pond,
        Channels.changelog,
        Channels.staff_announcements,
        Channels.mod_announcements,
        Channels.admin_announcements,
        Channels.staff_info
    ]


DuckPond = _DuckPond()


class _PythonNews(EnvConfig):
    EnvConfig.Config.env_prefix = "python_news__"

    channel: int = Channels.python_news
    webhook: int = Webhooks.python_news
    mail_lists: list[str]


PythonNews = _PythonNews()


class _VoiceGate(EnvConfig):
    EnvConfig.Config.env_prefix = "voice_gate__"

    bot_message_delete_delay: int
    minimum_activity_blocks: int
    minimum_days_member: int
    minimum_messages: int
    voice_ping_delete_delay: int


VoiceGate = _VoiceGate()


class _Branding(EnvConfig):
    EnvConfig.Config.env_prefix = "branding__"

    cycle_frequency: int


Branding = _Branding()


class _VideoPermission(EnvConfig):
    EnvConfig.Config.env_prefix = "video_permission__"

    default_permission_duration: int


VideoPermission = _VideoPermission()

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
