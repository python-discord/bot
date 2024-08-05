"""
Loads bot configuration from environment variables and `.env` files.

By default, the values defined in the classes are used, these can be overridden by an env var with the same name.

`.env` and `.env.server` files are used to populate env vars, if present.
"""
import os
from enum import Enum

from pydantic import BaseModel, computed_field
from pydantic_settings import BaseSettings


class EnvConfig(
    BaseSettings,
    env_file=(".env.server", ".env"),
    env_file_encoding = "utf-8",
    env_nested_delimiter = "__",
    extra="ignore",
):
    """Our default configuration for models that should load from .env files."""


class _Miscellaneous(EnvConfig):
    debug: bool = True
    file_logs: bool = False


Miscellaneous = _Miscellaneous()


FILE_LOGS = Miscellaneous.file_logs
DEBUG_MODE = Miscellaneous.debug


class _Bot(EnvConfig, env_prefix="bot_"):

    prefix: str = "!"
    sentry_dsn: str = ""
    token: str
    trace_loggers: str = "*"


Bot = _Bot()


class _Channels(EnvConfig, env_prefix="channels_"):

    announcements: int = 354619224620138496
    changelog: int = 748238795236704388
    mailing_lists: int = 704372456592506880
    python_events: int = 729674110270963822
    python_news: int = 704372456592506880
    reddit: int = 458224812528238616

    dev_contrib: int = 635950537262759947
    dev_core: int = 411200599653351425
    dev_log: int = 622895325144940554

    meta: int = 429409067623251969
    python_general: int = 267624335836053506

    python_help: int = 1035199133436354600

    attachment_log: int = 649243850006855680
    filter_log: int = 1014943924185473094
    message_log: int = 467752170159079424
    mod_log: int = 282638479504965634
    nomination_voting_archive: int = 833371042046148738
    user_log: int = 528976905546760203
    voice_log: int = 640292421988646961

    off_topic_0: int = 291284109232308226
    off_topic_1: int = 463035241142026251
    off_topic_2: int = 463035268514185226

    bot_commands: int = 267659945086812160
    discord_bots: int = 343944376055103488
    esoteric: int = 470884583684964352
    voice_gate: int = 764802555427029012
    code_jam_planning: int = 490217981872177157

    # Staff
    admins: int = 365960823622991872
    admin_spam: int = 563594791770914816
    defcon: int = 464469101889454091
    helpers: int = 385474242440986624
    incidents: int = 714214212200562749
    incidents_archive: int = 720668923636351037
    mod_alerts: int = 473092532147060736
    mod_meta: int = 775412552795947058
    mods: int = 305126844661760000
    nominations: int = 822920136150745168
    nomination_discussion: int = 798959130634747914
    nomination_voting: int = 822853512709931008
    organisation: int = 551789653284356126

    # Staff announcement channels
    admin_announcements: int = 749736155569848370
    mod_announcements: int = 372115205867700225
    staff_announcements: int = 464033278631084042
    staff_info: int = 396684402404622347
    staff_lounge: int = 464905259261755392

    # Voice Channels
    admins_voice: int = 500734494840717332
    code_help_voice_0: int = 751592231726481530
    code_help_voice_1: int = 764232549840846858
    general_voice_0: int = 751591688538947646
    general_voice_1: int = 799641437645701151
    staff_voice: int = 412375055910043655

    black_formatter: int = 846434317021741086

    # Voice Chat
    code_help_chat_0: int = 755154969761677312
    code_help_chat_1: int = 766330079135268884
    staff_voice_chat: int = 541638762007101470
    voice_chat_0: int = 412357430186344448
    voice_chat_1: int = 799647045886541885

    big_brother: int = 468507907357409333
    duck_pond: int = 637820308341915648
    roles: int = 851270062434156586

    rules: int = 693837295685730335


Channels = _Channels()


class _Roles(EnvConfig, env_prefix="roles_"):

    # Self-assignable roles, see the Subscribe cog
    advent_of_code: int = 518565788744024082
    announcements: int = 463658397560995840
    lovefest: int = 542431903886606399
    pyweek_announcements: int = 897568414044938310
    revival_of_code: int = 988801794668908655
    archived_channels_access: int = 1074780483776417964

    contributors: int = 295488872404484098
    partners: int = 323426753857191936
    python_community: int = 458226413825294336
    voice_verified: int = 764802720779337729

    # Streaming
    video: int = 764245844798079016

    # Staff
    admins: int = 267628507062992896
    core_developers: int = 587606783669829632
    code_jam_event_team: int = 787816728474288181
    devops: int = 409416496733880320
    domain_leads: int = 807415650778742785
    events_lead: int = 778361735739998228
    helpers: int = 267630620367257601
    moderators: int = 831776746206265384
    mod_team: int = 267629731250176001
    owners: int = 267627879762755584
    project_leads: int = 815701647526330398

    # Code Jam
    jammers: int = 737249140966162473

    # Patreon
    patreon_tier_1: int = 505040943800516611
    patreon_tier_2: int = 743399725914390631
    patreon_tier_3: int = 743400204367036520


Roles = _Roles()


class _Categories(EnvConfig, env_prefix="categories_"):

    logs: int = 468520609152892958
    moderators: int = 749736277464842262
    modmail: int = 714494672835444826
    appeals: int = 890331800025563216
    appeals_2: int = 895417395261341766
    voice: int = 356013253765234688

    # 2021 Summer Code Jam
    summer_code_jam: int = 861692638540857384
    python_help_system: int = 691405807388196926


Categories = _Categories()


class _Guild(EnvConfig, env_prefix="guild_"):

    id: int = 267624335836053506
    invite: str = "https://discord.gg/python"

    moderation_categories: tuple[int, ...] = (
        Categories.moderators,
        Categories.modmail,
        Categories.logs,
        Categories.appeals,
        Categories.appeals_2
    )
    moderation_channels: tuple[int, ...] = (Channels.admins, Channels.admin_spam, Channels.mods)
    modlog_blacklist: tuple[int, ...] = (
        Channels.attachment_log,
        Channels.message_log,
        Channels.mod_log,
        Channels.staff_voice,
        Channels.filter_log
    )
    reminder_whitelist: tuple[int, ...] = (Channels.bot_commands, Channels.dev_contrib, Channels.black_formatter)
    moderation_roles: tuple[int, ...] = (Roles.admins, Roles.mod_team, Roles.moderators, Roles.owners)
    staff_roles: tuple[int, ...] = (Roles.admins, Roles.helpers, Roles.mod_team, Roles.owners)


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


class _Webhooks(EnvConfig, env_prefix="webhooks_"):

    big_brother: Webhook = Webhook(id=569133704568373283, channel=Channels.big_brother)
    dev_log: Webhook = Webhook(id=680501655111729222, channel=Channels.dev_log)
    duck_pond: Webhook = Webhook(id=637821475327311927, channel=Channels.duck_pond)
    incidents: Webhook = Webhook(id=816650601844572212, channel=Channels.incidents)
    incidents_archive: Webhook = Webhook(id=720671599790915702, channel=Channels.incidents_archive)
    python_news: Webhook = Webhook(id=704381182279942324, channel=Channels.python_news)


Webhooks = _Webhooks()


class _BigBrother(EnvConfig, env_prefix="big_brother_"):

    header_message_limit: int = 15
    log_delay: int = 15


BigBrother = _BigBrother()


class _CodeBlock(EnvConfig, env_prefix="code_block_"):

    # The channels in which code blocks will be detected. They are not subject to a cooldown.
    channel_whitelist: tuple[int, ...] = (Channels.bot_commands,)
    # The channels which will be affected by a cooldown. These channels are also whitelisted.
    cooldown_channels: tuple[int, ...] = (Channels.python_general,)

    cooldown_seconds: int = 300
    minimum_lines: int = 4


CodeBlock = _CodeBlock()


class _HelpChannels(EnvConfig, env_prefix="help_channels_"):

    enable: bool = True
    idle_minutes: int = 60
    deleted_idle_minutes: int = 5
    # Roles which are allowed to use the command which makes channels dormant
    cmd_whitelist: tuple[int, ...] = Guild.moderation_roles


HelpChannels = _HelpChannels()


class _RedirectOutput(EnvConfig, env_prefix="redirect_output_"):

    delete_delay: int = 15
    delete_invocation: bool = True


RedirectOutput = _RedirectOutput()


class _DuckPond(EnvConfig, env_prefix="duck_pond_"):

    threshold: int = 7

    default_channel_blacklist: tuple[int, ...] = (
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
        Channels.staff_info,
    )

    extra_channel_blacklist: tuple[int, ...] = tuple()

    @computed_field
    @property
    def channel_blacklist(self) -> tuple[int, ...]:
        return self.default_channel_blacklist + self.extra_channel_blacklist

DuckPond = _DuckPond()


class _PythonNews(EnvConfig, env_prefix="python_news_"):

    channel: int = Webhooks.python_news.channel
    webhook: int = Webhooks.python_news.id
    mail_lists: tuple[str, ...] = ("python-ideas", "python-announce-list", "pypi-announce", "python-dev")


PythonNews = _PythonNews()


class _VoiceGate(EnvConfig, env_prefix="voice_gate_"):

    delete_after_delay: int = 60
    minimum_activity_blocks: int = 3
    minimum_days_member: int = 3
    minimum_messages: int = 50


VoiceGate = _VoiceGate()


class _Branding(EnvConfig, env_prefix="branding_"):

    cycle_frequency: int = 3


Branding = _Branding()


class _VideoPermission(EnvConfig, env_prefix="video_permission_"):

    default_permission_duration: int = 5


VideoPermission = _VideoPermission()


class _Redis(EnvConfig, env_prefix="redis_"):

    host: str = "redis.databases.svc.cluster.local"
    password: str = ""
    port: int = 6379
    use_fakeredis: bool = False  # If this is True, Bot will use fakeredis.aioredis


Redis = _Redis()


class _CleanMessages(EnvConfig, env_prefix="clean_"):

    message_limit: int = 10_000


CleanMessages = _CleanMessages()


class _Stats(EnvConfig, env_prefix="stats_"):

    presence_update_timeout: int = 30
    statsd_host: str = "graphite.default.svc.cluster.local"


Stats = _Stats()


class _Cooldowns(EnvConfig, env_prefix="cooldowns_"):

    tags: int = 60


Cooldowns = _Cooldowns()


class _Metabase(EnvConfig, env_prefix="metabase_"):

    username: str = ""
    password: str = ""
    base_url: str = "http://metabase.tooling.svc.cluster.local"
    public_url: str = "https://metabase.pydis.wtf"
    max_session_age: int = 20_160


Metabase = _Metabase()


class _BaseURLs(EnvConfig, env_prefix="urls_"):

    # Snekbox endpoints
    snekbox_eval_api: str = "http://snekbox.snekbox.svc.cluster.local/eval"

    # Discord API
    discord_api: str = "https://discordapp.com/api/v7/"

    # Misc endpoints
    bot_avatar: str = "https://raw.githubusercontent.com/python-discord/branding/main/logos/logo_circle/logo_circle.png"
    github_bot_repo: str = "https://github.com/python-discord/bot"

    # Site
    site_api: str = "http://site.web.svc.cluster.local/api"
    paste_url: str = "https://paste.pythondiscord.com"


BaseURLs = _BaseURLs()


class _URLs(_BaseURLs):

    # Discord API endpoints
    discord_invite_api: str = "".join([BaseURLs.discord_api, "invites"])

    # Base site vars
    connect_max_retries: int = 3
    connect_cooldown: int = 5

    site_logs_view: str = "https://pythondiscord.com/staff/bot/logs"


URLs = _URLs()


class _Emojis(EnvConfig, env_prefix="emojis_"):

    badge_bug_hunter: str = "<:bug_hunter_lvl1:743882896372269137>"
    badge_bug_hunter_level_2: str = "<:bug_hunter_lvl2:743882896611344505>"
    badge_early_supporter: str = "<:early_supporter:743882896909140058>"
    badge_hypesquad: str = "<:hypesquad_events:743882896892362873>"
    badge_hypesquad_balance: str = "<:hypesquad_balance:743882896460480625>"
    badge_hypesquad_bravery: str = "<:hypesquad_bravery:743882896745693335>"
    badge_hypesquad_brilliance: str = "<:hypesquad_brilliance:743882896938631248>"
    badge_partner: str = "<:partner:748666453242413136>"
    badge_staff: str = "<:discord_staff:743882896498098226>"
    badge_verified_bot_developer: str = "<:verified_bot_dev:743882897299210310>"
    badge_discord_certified_moderator: str = "<:discord_certified_moderator:1114130029547364434>"
    badge_bot_http_interactions: str = "<:bot_http_interactions:1114130379754975283>"
    badge_active_developer: str = "<:active_developer:1114130031036338176>"
    verified_bot: str = "<:verified_bot:811645219220750347>"
    bot: str = "<:bot:812712599464443914>"

    defcon_shutdown: str = "<:defcondisabled:470326273952972810>"
    defcon_unshutdown: str = "<:defconenabled:470326274213150730>"
    defcon_update: str = "<:defconsettingsupdated:470326274082996224>"

    failmail: str = "<:failmail:633660039931887616>"
    failed_file: str = "<:failed_file:1073298441968562226>"

    incident_actioned: str = "<:incident_actioned:714221559279255583>"
    incident_investigating: str = "<:incident_investigating:714224190928191551>"
    incident_unactioned: str = "<:incident_unactioned:714223099645526026>"

    status_dnd: str = "<:status_dnd:470326272082313216>"
    status_idle: str = "<:status_idle:470326266625785866>"
    status_offline: str = "<:status_offline:470326266537705472>"
    status_online: str = "<:status_online:470326272351010816>"

    ducky_dave: str = "<:ducky_dave:742058418692423772>"

    trashcan: str = "<:trashcan:637136429717389331>"

    bullet: str = "\u2022"
    check_mark: str = "\u2705"
    cross_mark: str = "\u274C"
    new: str = "\U0001F195"
    pencil: str = "\u270F"

    ok_hand: str = ":ok_hand:"


Emojis = _Emojis()


class Icons:
    """URLs to commonly used icons."""

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


class Colours:
    """Colour codes, mostly used to set discord.Embed colours."""

    blue: int = 0x3775a8
    bright_green: int = 0x01d277
    orange: int = 0xe67e22
    pink: int = 0xcf84e0
    purple: int = 0xb734eb
    soft_green: int = 0x68c290
    soft_orange: int = 0xf9cb54
    soft_red: int = 0xcd6d6d
    white: int = 0xfffffe
    yellow: int = 0xffd241


class _Keys(EnvConfig, env_prefix="api_keys_"):

    github: str = ""
    site_api: str = ""


Keys = _Keys()


BOT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(BOT_DIR, os.pardir))

# Default role combinations
MODERATION_ROLES = Guild.moderation_roles
STAFF_ROLES = Guild.staff_roles
STAFF_PARTNERS_COMMUNITY_ROLES = STAFF_ROLES + (Roles.partners, Roles.python_community)

# Channel combinations
MODERATION_CHANNELS = Guild.moderation_channels

# Category combinations
MODERATION_CATEGORIES = Guild.moderation_categories

# Git SHA for Sentry
GIT_SHA = os.environ.get("GIT_SHA", "development")


# Bot replies
NEGATIVE_REPLIES = (
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
)

POSITIVE_REPLIES = (
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
)

ERROR_REPLIES = (
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
)
