"""
Loads bot configuration from environment variables and `.env` files.

By default, the values defined in the classes are used, these can be overridden by an env var with the same name.

`.env` and `.env.server` files are used to populate env vars, if present.
"""
import os
from enum import Enum

from pydantic import BaseModel, BaseSettings, root_validator


class EnvConfig(BaseSettings):
    """Our default configuration for models that should load from .env files."""

    class Config:
        """Specify what .env files to load, and how to load them."""

        env_file = ".env.server", ".env",
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"


class _Miscellaneous(EnvConfig):
    debug = True
    file_logs = False


Miscellaneous = _Miscellaneous()


FILE_LOGS = Miscellaneous.file_logs
DEBUG_MODE = Miscellaneous.debug


class _Bot(EnvConfig):
    EnvConfig.Config.env_prefix = "bot_"

    prefix = "!"
    sentry_dsn = ""
    token = ""
    trace_loggers = "*"


Bot = _Bot()


class _Channels(EnvConfig):
    EnvConfig.Config.env_prefix = "channels_"

    announcements = 354619224620138496
    changelog = 748238795236704388
    mailing_lists = 704372456592506880
    python_events = 729674110270963822
    python_news = 704372456592506880
    reddit = 458224812528238616

    dev_contrib = 635950537262759947
    dev_core = 411200599653351425
    dev_log = 622895325144940554

    meta = 429409067623251969
    python_general = 267624335836053506

    python_help = 1035199133436354600

    attachment_log = 649243850006855680
    filter_log = 1014943924185473094
    message_log = 467752170159079424
    mod_log = 282638479504965634
    nomination_voting_archive = 833371042046148738
    user_log = 528976905546760203
    voice_log = 640292421988646961

    off_topic_0 = 291284109232308226
    off_topic_1 = 463035241142026251
    off_topic_2 = 463035268514185226

    bot_commands = 267659945086812160
    discord_bots = 343944376055103488
    esoteric = 470884583684964352
    voice_gate = 764802555427029012
    code_jam_planning = 490217981872177157

    # Staff
    admins = 365960823622991872
    admin_spam = 563594791770914816
    defcon = 464469101889454091
    helpers = 385474242440986624
    incidents = 714214212200562749
    incidents_archive = 720668923636351037
    mod_alerts = 473092532147060736
    mod_meta = 775412552795947058
    mods = 305126844661760000
    nominations = 822920136150745168
    nomination_discussion = 798959130634747914
    nomination_voting = 822853512709931008
    organisation = 551789653284356126

    # Staff announcement channels
    admin_announcements = 749736155569848370
    mod_announcements = 372115205867700225
    staff_announcements = 464033278631084042
    staff_info = 396684402404622347
    staff_lounge = 464905259261755392

    # Voice Channels
    admins_voice = 500734494840717332
    code_help_voice_0 = 751592231726481530
    code_help_voice_1 = 764232549840846858
    general_voice_0 = 751591688538947646
    general_voice_1 = 799641437645701151
    staff_voice = 412375055910043655

    black_formatter = 846434317021741086

    # Voice Chat
    code_help_chat_0 = 755154969761677312
    code_help_chat_1 = 766330079135268884
    staff_voice_chat = 541638762007101470
    voice_chat_0 = 412357430186344448
    voice_chat_1 = 799647045886541885

    big_brother = 468507907357409333
    duck_pond = 637820308341915648
    roles = 851270062434156586

    rules = 693837295685730335


Channels = _Channels()


class _Roles(EnvConfig):

    EnvConfig.Config.env_prefix = "roles_"

    # Self-assignable roles, see the Subscribe cog
    advent_of_code = 518565788744024082
    announcements = 463658397560995840
    lovefest = 542431903886606399
    pyweek_announcements = 897568414044938310
    revival_of_code = 988801794668908655
    legacy_help_channels_access = 1074780483776417964

    contributors = 295488872404484098
    help_cooldown = 699189276025421825
    partners = 323426753857191936
    python_community = 458226413825294336
    voice_verified = 764802720779337729

    # Streaming
    video = 764245844798079016

    # Staff
    admins = 267628507062992896
    core_developers = 587606783669829632
    code_jam_event_team = 787816728474288181
    devops = 409416496733880320
    domain_leads = 807415650778742785
    events_lead = 778361735739998228
    helpers = 267630620367257601
    moderators = 831776746206265384
    mod_team = 267629731250176001
    owners = 267627879762755584
    project_leads = 815701647526330398

    # Code Jam
    jammers = 737249140966162473

    # Patreon
    patreon_tier_1 = 505040943800516611
    patreon_tier_2 = 743399725914390631
    patreon_tier_3 = 743400204367036520


Roles = _Roles()


class _Categories(EnvConfig):
    EnvConfig.Config.env_prefix = "categories_"

    logs = 468520609152892958
    moderators = 749736277464842262
    modmail = 714494672835444826
    appeals = 890331800025563216
    appeals_2 = 895417395261341766
    voice = 356013253765234688

    # 2021 Summer Code Jam
    summer_code_jam = 861692638540857384
    python_help_system = 691405807388196926


Categories = _Categories()


class _Guild(EnvConfig):
    EnvConfig.Config.env_prefix = "guild_"

    id = 267624335836053506
    invite = "https://discord.gg/python"

    moderation_categories = [
        Categories.moderators,
        Categories.modmail,
        Categories.logs,
        Categories.appeals,
        Categories.appeals_2
    ]
    moderation_channels = [Channels.admins, Channels.admin_spam, Channels.mods]
    modlog_blacklist = [
        Channels.attachment_log,
        Channels.message_log,
        Channels.mod_log,
        Channels.staff_voice,
        Channels.filter_log
    ]
    reminder_whitelist = [Channels.bot_commands, Channels.dev_contrib, Channels.black_formatter]
    moderation_roles = [Roles.admins, Roles.mod_team, Roles.moderators, Roles.owners]
    staff_roles = [Roles.admins, Roles.helpers, Roles.mod_team, Roles.owners]


Guild = _Guild()


class Event(Enum):
    """
    Discord.py event names.

    This does not include every event (for example, raw events aren't here), only events used in ModLog for now.
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
    """The time periods threads can have the archive time set to."""

    HOUR = 60
    DAY = 1440
    THREE_DAY = 4320
    WEEK = 10080


class Webhook(BaseModel):
    """A base class for all webhooks."""

    id: int
    channel: int


class _Webhooks(EnvConfig):
    EnvConfig.Config.env_prefix = "webhooks_"

    big_brother: Webhook = Webhook(id=569133704568373283, channel=Channels.big_brother)
    dev_log: Webhook = Webhook(id=680501655111729222, channel=Channels.dev_log)
    duck_pond: Webhook = Webhook(id=637821475327311927, channel=Channels.duck_pond)
    incidents: Webhook = Webhook(id=816650601844572212, channel=Channels.incidents)
    incidents_archive: Webhook = Webhook(id=720671599790915702, channel=Channels.incidents_archive)
    python_news: Webhook = Webhook(id=704381182279942324, channel=Channels.python_news)


Webhooks = _Webhooks()


class _BigBrother(EnvConfig):
    EnvConfig.Config.env_prefix = "big_brother_"

    header_message_limit = 15
    log_delay = 15


BigBrother = _BigBrother()


class _CodeBlock(EnvConfig):
    EnvConfig.Config.env_prefix = "code_block_"

    # The channels in which code blocks will be detected. They are not subject to a cooldown.
    channel_whitelist: list[int] = [Channels.bot_commands]
    # The channels which will be affected by a cooldown. These channels are also whitelisted.
    cooldown_channels: list[int] = [Channels.python_general]

    cooldown_seconds = 300
    minimum_lines = 4


CodeBlock = _CodeBlock()


class _Colours(EnvConfig):
    EnvConfig.Config.env_prefix = "colours_"

    blue = 0x3775a8
    bright_green = 0x01d277
    orange = 0xe67e22
    pink = 0xcf84e0
    purple = 0xb734eb
    soft_green = 0x68c290
    soft_orange = 0xf9cb54
    soft_red = 0xcd6d6d
    white = 0xfffffe
    yellow = 0xffd241

    @root_validator(pre=True)
    def parse_hex_values(cls, values: dict) -> dict:  # noqa: N805
        """Convert hex strings to ints."""
        for key, value in values.items():
            values[key] = int(value, 16)
        return values


Colours = _Colours()


class _HelpChannels(EnvConfig):
    EnvConfig.Config.env_prefix = "help_channels_"

    enable = True
    idle_minutes = 60
    deleted_idle_minutes = 5
    # Roles which are allowed to use the command which makes channels dormant
    cmd_whitelist = Guild.moderation_roles


HelpChannels = _HelpChannels()


class _RedirectOutput(EnvConfig):
    EnvConfig.Config.env_prefix = "redirect_output_"

    delete_delay = 15
    delete_invocation = True


RedirectOutput = _RedirectOutput()


class _DuckPond(EnvConfig):
    EnvConfig.Config.env_prefix = "duck_pond_"

    threshold = 7

    channel_blacklist: list[int] = [
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
    EnvConfig.Config.env_prefix = "python_news_"

    channel: int = Webhooks.python_news.channel
    webhook: int = Webhooks.python_news.id
    mail_lists = ["python-ideas", "python-announce-list", "pypi-announce", "python-dev"]


PythonNews = _PythonNews()


class _VoiceGate(EnvConfig):
    EnvConfig.Config.env_prefix = "voice_gate_"

    bot_message_delete_delay = 10
    minimum_activity_blocks = 3
    minimum_days_member = 3
    minimum_messages = 50
    voice_ping_delete_delay = 60


VoiceGate = _VoiceGate()


class _Branding(EnvConfig):
    EnvConfig.Config.env_prefix = "branding_"

    cycle_frequency = 3


Branding = _Branding()


class _VideoPermission(EnvConfig):
    EnvConfig.Config.env_prefix = "video_permission_"

    default_permission_duration = 5


VideoPermission = _VideoPermission()


class _Redis(EnvConfig):
    EnvConfig.Config.env_prefix = "redis_"

    host = "redis.default.svc.cluster.local"
    password = ""
    port = 6379
    use_fakeredis = False  # If this is True, Bot will use fakeredis.aioredis


Redis = _Redis()


class _CleanMessages(EnvConfig):
    EnvConfig.Config.env_prefix = "clean_"

    message_limit = 10_000


CleanMessages = _CleanMessages()


class _Stats(EnvConfig):
    EnvConfig.Config.env_prefix = "stats_"

    presence_update_timeout = 30
    statsd_host = "graphite.default.svc.cluster.local"


Stats = _Stats()


class _Cooldowns(EnvConfig):
    EnvConfig.Config.env_prefix = "cooldowns_"

    tags = 60


Cooldowns = _Cooldowns()


class _Metabase(EnvConfig):
    EnvConfig.Config.env_prefix = "metabase_"

    username = ""
    password = ""
    base_url = "http://metabase.default.svc.cluster.local"
    public_url = "https://metabase.pythondiscord.com"
    max_session_age = 20_160


Metabase = _Metabase()


class _BaseURLs(EnvConfig):
    EnvConfig.Config.env_prefix = "urls_"

    # Snekbox endpoints
    snekbox_eval_api = "http://snekbox.default.svc.cluster.local/eval"

    # Discord API
    discord_api = "https://discordapp.com/api/v7/"

    # Misc endpoints
    bot_avatar = "https://raw.githubusercontent.com/python-discord/branding/main/logos/logo_circle/logo_circle.png"

    github_bot_repo = "https://github.com/python-discord/bot"

    # Site
    site_api = "http://site.default.svc.cluster.local/api"

    paste_url = "https://paste.pythondiscord.com"


BaseURLs = _BaseURLs()


class _URLs(_BaseURLs):

    # Discord API endpoints
    discord_invite_api: str = "".join([BaseURLs.discord_api, "invites"])

    # Base site vars
    connect_max_retries = 3
    connect_cooldown = 5

    site_logs_view: str = "https://pythondiscord.com/staff/bot/logs"


URLs = _URLs()


class _Emojis(EnvConfig):
    EnvConfig.Config.env_prefix = "emojis_"

    badge_bug_hunter = "<:bug_hunter_lvl1:743882896372269137>"
    badge_bug_hunter_level_2 = "<:bug_hunter_lvl2:743882896611344505>"
    badge_early_supporter = "<:early_supporter:743882896909140058>"
    badge_hypesquad = "<:hypesquad_events:743882896892362873>"
    badge_hypesquad_balance = "<:hypesquad_balance:743882896460480625>"
    badge_hypesquad_bravery = "<:hypesquad_bravery:743882896745693335>"
    badge_hypesquad_brilliance = "<:hypesquad_brilliance:743882896938631248>"
    badge_partner = "<:partner:748666453242413136>"
    badge_staff = "<:discord_staff:743882896498098226>"
    badge_verified_bot_developer = "<:verified_bot_dev:743882897299210310>"
    badge_discord_certified_moderator = "<:discord_certified_moderator:1114130029547364434>"
    badge_bot_http_interactions = "<:bot_http_interactions:1114130379754975283>"
    badge_active_developer = "<:active_developer:1114130031036338176>"
    verified_bot = "<:verified_bot:811645219220750347>"
    bot = "<:bot:812712599464443914>"

    defcon_shutdown = "<:defcondisabled:470326273952972810>"
    defcon_unshutdown = "<:defconenabled:470326274213150730>"
    defcon_update = "<:defconsettingsupdated:470326274082996224>"

    failmail = "<:failmail:633660039931887616>"
    failed_file = "<:failed_file:1073298441968562226>"

    incident_actioned = "<:incident_actioned:714221559279255583>"
    incident_investigating = "<:incident_investigating:714224190928191551>"
    incident_unactioned = "<:incident_unactioned:714223099645526026>"

    status_dnd = "<:status_dnd:470326272082313216>"
    status_idle = "<:status_idle:470326266625785866>"
    status_offline = "<:status_offline:470326266537705472>"
    status_online = "<:status_online:470326272351010816>"

    ducky_dave = "<:ducky_dave:742058418692423772>"

    trashcan = "<:trashcan:637136429717389331>"

    bullet = "\u2022"
    check_mark = "\u2705"
    cross_mark = "\u274C"
    new = "\U0001F195"
    pencil = "\u270F"

    ok_hand = ":ok_hand:"


Emojis = _Emojis()


class _Icons(EnvConfig):
    EnvConfig.Config.env_prefix = "icons_"

    crown_blurple = "https://cdn.discordapp.com/emojis/469964153289965568.png"
    crown_green = "https://cdn.discordapp.com/emojis/469964154719961088.png"
    crown_red = "https://cdn.discordapp.com/emojis/469964154879344640.png"

    defcon_denied = "https://cdn.discordapp.com/emojis/472475292078964738.png"
    defcon_shutdown = "https://cdn.discordapp.com/emojis/470326273952972810.png"
    defcon_unshutdown = "https://cdn.discordapp.com/emojis/470326274213150730.png"
    defcon_update = "https://cdn.discordapp.com/emojis/472472638342561793.png"

    filtering = "https://cdn.discordapp.com/emojis/472472638594482195.png"

    green_checkmark = "https://raw.githubusercontent.com/python-discord/branding/main/icons/checkmark/green-checkmark-dist.png"
    green_questionmark = "https://raw.githubusercontent.com/python-discord/branding/main/icons/checkmark/green-question-mark-dist.png"
    guild_update = "https://cdn.discordapp.com/emojis/469954765141442561.png"

    hash_blurple = "https://cdn.discordapp.com/emojis/469950142942806017.png"
    hash_green = "https://cdn.discordapp.com/emojis/469950144918585344.png"
    hash_red = "https://cdn.discordapp.com/emojis/469950145413251072.png"

    message_bulk_delete = "https://cdn.discordapp.com/emojis/469952898994929668.png"
    message_delete = "https://cdn.discordapp.com/emojis/472472641320648704.png"
    message_edit = "https://cdn.discordapp.com/emojis/472472638976163870.png"

    pencil = "https://cdn.discordapp.com/emojis/470326272401211415.png"

    questionmark = "https://cdn.discordapp.com/emojis/512367613339369475.png"

    remind_blurple = "https://cdn.discordapp.com/emojis/477907609215827968.png"
    remind_green = "https://cdn.discordapp.com/emojis/477907607785570310.png"
    remind_red = "https://cdn.discordapp.com/emojis/477907608057937930.png"

    sign_in = "https://cdn.discordapp.com/emojis/469952898181234698.png"
    sign_out = "https://cdn.discordapp.com/emojis/469952898089091082.png"

    superstarify = "https://cdn.discordapp.com/emojis/636288153044516874.png"
    unsuperstarify = "https://cdn.discordapp.com/emojis/636288201258172446.png"

    token_removed = "https://cdn.discordapp.com/emojis/470326273298792469.png"  # noqa: S105

    user_ban = "https://cdn.discordapp.com/emojis/469952898026045441.png"
    user_timeout = "https://cdn.discordapp.com/emojis/472472640100106250.png"
    user_unban = "https://cdn.discordapp.com/emojis/469952898692808704.png"
    user_untimeout = "https://cdn.discordapp.com/emojis/472472639206719508.png"
    user_update = "https://cdn.discordapp.com/emojis/469952898684551168.png"
    user_verified = "https://cdn.discordapp.com/emojis/470326274519334936.png"
    user_warn = "https://cdn.discordapp.com/emojis/470326274238447633.png"

    voice_state_blue = "https://cdn.discordapp.com/emojis/656899769662439456.png"
    voice_state_green = "https://cdn.discordapp.com/emojis/656899770094452754.png"
    voice_state_red = "https://cdn.discordapp.com/emojis/656899769905709076.png"


Icons = _Icons()


class _Keys(EnvConfig):

    EnvConfig.Config.env_prefix = "api_keys_"

    github = ""
    site_api = ""


Keys = _Keys()


BOT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BOT_DIR, os.pardir))

# Default role combinations
MODERATION_ROLES = Guild.moderation_roles
STAFF_ROLES = Guild.staff_roles
STAFF_PARTNERS_COMMUNITY_ROLES = STAFF_ROLES + [Roles.partners, Roles.python_community]

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
