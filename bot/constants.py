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
import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, BaseSettings, Field, root_validator

# Will add a check for the required keys

env_file_path = Path(__file__).parent.parent / ".env"
server_env_file_path = Path(__file__).parent.parent / ".env.server"


class EnvConfig(BaseSettings):
    class Config:
        env_file = env_file_path, server_env_file_path,
        env_file_encoding = 'utf-8'


class _Miscellaneous(EnvConfig):
    debug: str = Field(env="BOT_DEBUG", default="true")
    file_logs: str = Field(env="FILE_LOGS", default="false")


Miscellaneous = _Miscellaneous()


FILE_LOGS = Miscellaneous.file_logs.lower() == "true"
DEBUG_MODE = Miscellaneous.debug.lower() == "true"


class _Bot(EnvConfig):
    EnvConfig.Config.env_prefix = "bot__"

    prefix: str = Field(default="!")
    sentry_dsn: str = Field(default="", env="BOT_SENTRY_DSN")
    token: str = Field(default="", env="BOT_TOKEN")
    trace_loggers = Field(default="*", env="BOT_TRACE_LOGGERS")


Bot = _Bot()


class _Channels(EnvConfig):
    EnvConfig.Config.env_prefix = "channels__"

    announcements: int = Field(default=354619224620138496)
    changelog: int = Field(default=748238795236704388)
    mailing_lists: int = Field(default=704372456592506880)
    python_events: int = Field(default=729674110270963822)
    python_news: int = Field(default=704372456592506880)
    reddit: int = Field(default=458224812528238616)

    dev_contrib: int = Field(default=635950537262759947)
    dev_core: int = Field(default=411200599653351425)
    dev_log: int = Field(default=622895325144940554)

    meta: int = Field(default=429409067623251969)
    python_general: int = Field(default=267624335836053506)

    help_system_forum: int = Field(default=1035199133436354600)

    attachment_log: int = Field(default=649243850006855680)
    filter_log: int = Field(default=1014943924185473094)
    message_log: int = Field(default=467752170159079424)
    mod_log: int = Field(default=282638479504965634)
    nomination_archive: int = Field(default=833371042046148738)
    user_log: int = Field(default=528976905546760203)
    voice_log: int = Field(default=640292421988646961)

    off_topic_0: int = Field(default=291284109232308226)
    off_topic_1: int = Field(default=463035241142026251)
    off_topic_2: int = Field(default=463035268514185226)

    bot_commands: int = Field(default=267659945086812160)
    discord_bots: int = Field(default=343944376055103488)
    esoteric: int = Field(default=470884583684964352)
    voice_gate: int = Field(default=764802555427029012)
    code_jam_planning: int = Field(default=490217981872177157)

    # Staff
    admins: int = Field(default=365960823622991872)
    admin_spam: int = Field(default=563594791770914816)
    defcon: int = Field(default=464469101889454091)
    helpers: int = Field(default=385474242440986624)
    incidents: int = Field(default=714214212200562749)
    incidents_archive: int = Field(default=720668923636351037)
    mod_alerts: int = Field(default=473092532147060736)
    mod_meta: int = Field(default=775412552795947058)
    mods: int = Field(default=305126844661760000)
    nominations: int = Field(default=822920136150745168)
    nomination_voting: int = Field(default=822853512709931008)
    organisation: int = Field(default=551789653284356126)

    # Staff announcement channels
    admin_announcements: int = Field(default=749736155569848370)
    mod_announcements: int = Field(default=372115205867700225)
    staff_announcements: int = Field(default=464033278631084042)
    staff_info: int = Field(default=396684402404622347)
    staff_lounge: int = Field(default=464905259261755392)

    # Voice Channels
    admins_voice: int = Field(default=500734494840717332)
    code_help_voice_0: int = Field(default=751592231726481530)
    code_help_voice_1: int = Field(default=764232549840846858)
    general_voice_0: int = Field(default=751591688538947646)
    general_voice_1: int = Field(default=799641437645701151)
    staff_voice: int = Field(default=412375055910043655)

    black_formatter: int = Field(default=846434317021741086)

    # Voice Chat
    code_help_chat_0: int = Field(default=755154969761677312)
    code_help_chat_1: int = Field(default=766330079135268884)
    staff_voice_chat: int = Field(default=541638762007101470)
    voice_chat_0: int = Field(default=412357430186344448)
    voice_chat_1: int = Field(default=799647045886541885)

    big_brother_logs: int = Field(default=468507907357409333)
    duck_pond: int = Field(default=637820308341915648)
    roles: int = Field(default=851270062434156586)


Channels = _Channels()


class _Roles(EnvConfig):

    EnvConfig.Config.env_prefix = "roles__"

    # Self-assignable roles, see the Subscribe cog
    advent_of_code: int = Field(default=518565788744024082)
    announcements: int = Field(default=463658397560995840)
    lovefest: int = Field(default=542431903886606399)
    pyweek_announcements: int = Field(default=897568414044938310)
    revival_of_code: int = Field(default=988801794668908655)
    legacy_help_channels_access: int = Field(default=1074780483776417964)

    contributors: int = Field(default=295488872404484098)
    help_cooldown: int = Field(default=699189276025421825)
    muted: int = Field(default=277914926603829249)
    partners: int = Field(default=323426753857191936)
    python_community: int = Field(default=458226413825294336)
    sprinters: int = Field(default=758422482289426471)
    voice_verified: int = Field(default=764802720779337729)

    # Streaming
    video: int = Field(default=764245844798079016)

    # Staff
    admins: int = Field(default=267628507062992896)
    core_developers: int = Field(default=587606783669829632)
    code_jam_event_team: int = Field(default=787816728474288181)
    devops: int = Field(default=409416496733880320)
    domain_leads: int = Field(default=807415650778742785)
    events_lead: int = Field(default=778361735739998228)
    helpers: int = Field(default=267630620367257601)
    moderators: int = Field(default=831776746206265384)
    mod_team: int = Field(default=267629731250176001)
    owners: int = Field(default=267627879762755584)
    project_leads: int = Field(default=815701647526330398)

    # Code Jam
    jammers: int = Field(default=737249140966162473)

    # Patreon
    patreon_tier_1: int = Field(default=505040943800516611)
    patreon_tier_2: int = Field(default=743399725914390631)
    patreon_tier_3: int = Field(default=743400204367036520)


Roles = _Roles()


class _Categories(EnvConfig):
    EnvConfig.Config.env_prefix = "categories__"

    logs: int = Field(default=468520609152892958)
    moderators: int = Field(default=749736277464842262)
    modmail: int = Field(default=714494672835444826)
    appeals: int = Field(default=890331800025563216)
    appeals2: int = Field(default=895417395261341766)
    voice: int = Field(default=356013253765234688)

    # 2021 Summer Code Jam
    summer_code_jam: int = Field(default=861692638540857384)


Categories = _Categories()


class _Guild(EnvConfig):
    EnvConfig.Config.env_prefix = "guild__"

    id: int = Field(default=267624335836053506, env="GUILD_ID")
    invite: str = Field(default="https://discord.gg/python")

    moderation_categories = [
        Categories.moderators,
        Categories.modmail,
        Categories.logs,
        Categories.appeals,
        Categories.appeals2
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


class Webhook(BaseModel):
    id: int
    channel: Optional[int]


class _Webhooks(EnvConfig):
    EnvConfig.Config.env_prefix = "webhooks__"
    EnvConfig.Config.env_nested_delimiter = '__'

    big_brother: Webhook = Webhook(id=569133704568373283, channel=Channels.big_brother_logs)
    dev_log: Webhook = Webhook(id=680501655111729222, channel=Channels.dev_log)
    duck_pond: Webhook = Webhook(id=637821475327311927, channel=Channels.duck_pond)
    incidents: Webhook = Webhook(id=816650601844572212, channel=Channels.incidents)
    incidents_archive: Webhook = Webhook(id=720671599790915702, channel=Channels.incidents_archive)
    python_news: Webhook = Webhook(id=704381182279942324, channel=Channels.python_news)


Webhooks = _Webhooks()


class _BigBrother(EnvConfig):
    EnvConfig.Config.env_prefix = "big_brother__"

    header_message_limit: int = Field(default=15)
    log_delay: int = Field(default=15)


BigBrother = _BigBrother()


class _CodeBlock(EnvConfig):
    EnvConfig.Config.env_prefix = "code_block__"

    # The channels in which code blocks will be detected. They are not subject to a cooldown.
    channel_whitelist: list[int] = [Channels.bot_commands]
    # The channels which will be affected by a cooldown. These channels are also whitelisted.
    cooldown_channels: list[int] = [Channels.python_general]

    cooldown_seconds: int = Field(default=300)
    minimum_lines: int = Field(default=4)


CodeBlock = _CodeBlock()


class _Colours(EnvConfig):
    EnvConfig.Config.env_prefix = "colours__"

    blue: int = Field(default=0x3775a8)
    bright_green: int = Field(default=0x01d277)
    orange: int = Field(default=0xe67e22)
    pink: int = Field(default=0xcf84e0)
    purple: int = Field(default=0xb734eb)
    soft_green: int = Field(default=0x68c290)
    soft_orange: int = Field(default=0xf9cb54)
    soft_red: int = Field(default=0xcd6d6d)
    white: int = Field(default=0xfffffe)
    yellow: int = Field(default=0xffd241)

    @root_validator(pre=True)
    def parse_hex_values(cls, values):
        for key, value in values.items():
            values[key] = int(value, 16)
        return values


Colours = _Colours()


class _Free(EnvConfig):
    EnvConfig.Config.env_prefix = "free__"

    activity_timeout: int = Field(default=600)
    cooldown_per: float = Field(default=60.0)
    cooldown_rate: int = Field(default=1)


Free = _Free()


class Punishment(BaseModel):
    remove_after: int = Field(default=600)
    role_id: int = Roles.muted


class Rule(BaseModel):
    interval: int
    max: int


# Some help in choosing an appropriate name for this is appreciated
class ExtendedRule(Rule):
    max_consecutive: int


class Rules(BaseModel):
    attachments: Rule = Rule(interval=10, max=10)
    burst: Rule = Rule(interval=10, max=7)
    chars: Rule = Rule(interval=5, max=200)
    discord_emojis: Rule = Rule(interval=10, max=20)
    duplicates: Rule = Rule(interval=10, max=3)
    links: Rule = Rule(interval=10, max=10)
    mentions: Rule = Rule(interval=10, max=5)
    newlines: ExtendedRule = ExtendedRule(interval=10, max=100, max_consecutive=10)
    role_mentions: Rule = Rule(interval=10, max=3)


class _AntiSpam(EnvConfig):
    EnvConfig.Config.env_prefix = 'anti_spam__'
    EnvConfig.Config.env_nested_delimiter = '__'

    cache_size: int = Field(default=100)

    clean_offending: bool = Field(default=True)
    ping_everyone: bool = Field(default=True)

    punishment: Punishment = Field(default=Punishment())
    rules: Rules = Field(default=Rules())


AntiSpam = _AntiSpam()


class _HelpChannels(EnvConfig):
    EnvConfig.Config.env_prefix = 'help_channels__'

    enable: bool = Field(default=True)
    idle_minutes: int = Field(default=30)
    deleted_idle_minutes: int = Field(default=5)
    # Roles which are allowed to use the command which makes channels dormant
    cmd_whitelist: list[int] = [Roles.helpers]


HelpChannels = _HelpChannels()


class _RedirectOutput(EnvConfig):
    EnvConfig.Config.env_prefix = "redirect_output__"

    delete_delay: int = Field(default=15)
    delete_invocation: bool = Field(default=True)


RedirectOutput = _RedirectOutput()


class _DuckPond(EnvConfig):
    EnvConfig.Config.env_prefix = 'duck_pond__'

    threshold: int = Field(default=7)

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

    channel: int = Webhooks.python_news.channel
    webhook: int = Webhooks.python_news.id
    mail_lists: list[str] = Field(default=['python-ideas', 'python-announce-list', 'pypi-announce', 'python-dev'])


PythonNews = _PythonNews()


class _VoiceGate(EnvConfig):
    EnvConfig.Config.env_prefix = "voice_gate__"

    bot_message_delete_delay: int = Field(default=10)
    minimum_activity_blocks: int = Field(default=3)
    minimum_days_member: int = Field(default=3)
    minimum_messages: int = Field(default=50)
    voice_ping_delete_delay: int = Field(default=60)


VoiceGate = _VoiceGate()


class _Branding(EnvConfig):
    EnvConfig.Config.env_prefix = "branding__"

    cycle_frequency: int = Field(default=3)


Branding = _Branding()


class _VideoPermission(EnvConfig):
    EnvConfig.Config.env_prefix = "video_permission__"

    default_permission_duration: int = Field(default=5)


VideoPermission = _VideoPermission()


class _Redis(EnvConfig):
    EnvConfig.Config.env_prefix = "redis__"

    host: str = Field(default="redis.default.svc.cluster.local")
    password = Field(default="", env="REDIS_PASSWORD")
    port: int = Field(default=6379)
    use_fakeredis: bool = Field(default=False)  # If this is True, Bot will use fakeredis.aioredis


Redis = _Redis()


class _CleanMessages(EnvConfig):
    EnvConfig.Config.env_prefix = "clean__"

    message_limit: int = Field(default=10_000)


CleanMessages = _CleanMessages()


class _Stats(EnvConfig):
    EnvConfig.Config.env_prefix = "stats__"

    presence_update_timeout: int = Field(default=30)
    statsd_host: str = Field(default="graphite.default.svc.cluster.local")


Stats = _Stats()


class _Cooldowns(EnvConfig):
    EnvConfig.Config.env_prefix = "cooldowns__"

    tags: int = Field(default=60)


Cooldowns = _Cooldowns()


class _Metabase(EnvConfig):
    EnvConfig.Config.env_prefix = "metabase__"

    username = Field(default="", env="METABASE_USERNAME")
    password = Field(default="", env="METABASE_PASSWORD")
    base_url: str = Field(default="http://metabase.default.svc.cluster.local")
    public_url: str = Field(default="https://metabase.pythondiscord.com")
    max_session_age: int = Field(default=20_160)


Metabase = _Metabase()


class _BaseURLs(EnvConfig):
    EnvConfig.Config.env_prefix = "urls__"

    # Snekbox endpoints
    snekbox_eval_api = Field(default="http://snekbox.default.svc.cluster.local/eval", env="SNEKBOX_EVAL_API")
    snekbox_311_eval_api = Field(default="http://snekbox-311.default.svc.cluster.local/eval", env="SNEKBOX_311_EVAL_API")

    # Discord API
    discord_api: str = Field(default="https://discordapp.com/api/v7/")

    # Misc endpoints
    bot_avatar: str = Field(
        default="https://raw.githubusercontent.com/python-discord/branding/main/logos/logo_circle/logo_circle.png"
    )
    github_bot_repo: str = Field(default="https://github.com/python-discord/bot")

    # Site
    site: str = Field(default="pythondiscord.com")
    site_schema: str = Field(default="https://")
    site_api: str = Field(default="site.default.svc.cluster.local/api")
    site_api_schema: str = Field(default="http://")


BaseURLs = _BaseURLs()


class _URLs(_BaseURLs):

    # Discord API endpoints
    discord_invite_api: str = "".join([BaseURLs.discord_api, "invites"])

    # Base site vars
    connect_max_retries: int = Field(default=3)
    connect_cooldown: int = Field(default=5)

    site_staff: str = "".join([BaseURLs.site_schema, BaseURLs.site, "/staff"])
    site_paste = "".join(["paste.", BaseURLs.site])

    # Site endpoints
    site_logs_view: str = "".join([BaseURLs.site_schema, BaseURLs.site, "/staff/bot/logs"])
    paste_service: str = "".join([BaseURLs.site_schema, "paste.", BaseURLs.site, "/{key}"])


URLs = _URLs()


class _Emojis(EnvConfig):
    EnvConfig.Config.env_prefix = "emojis__"

    badge_bug_hunter: str = Field(default="<:bug_hunter_lvl1:743882896372269137>")
    badge_bug_hunter_level_2: str = Field(default="<:bug_hunter_lvl2:743882896611344505>")
    badge_early_supporter: str = Field(default="<:early_supporter:743882896909140058>")
    badge_hypesquad: str = Field(default="<:hypesquad_events:743882896892362873>")
    badge_hypesquad_balance: str = Field(default="<:hypesquad_balance:743882896460480625>")
    badge_hypesquad_bravery: str = Field(default="<:hypesquad_bravery:743882896745693335>")
    badge_hypesquad_brilliance: str = Field(default="<:hypesquad_brilliance:743882896938631248>")
    badge_partner: str = Field(default="<:partner:748666453242413136>")
    badge_staff: str = Field(default="<:discord_staff:743882896498098226>")
    badge_verified_bot_developer: str = Field(default="<:verified_bot_dev:743882897299210310>")
    verified_bot: str = Field(default="<:verified_bot:811645219220750347>")
    bot: str = Field(default="<:bot:812712599464443914>")

    defcon_shutdown: str = Field(default="<:defcondisabled:470326273952972810>")  # noqa: E704
    defcon_unshutdown: str = Field(default="<:defconenabled:470326274213150730>")  # noqa: E704
    defcon_update: str = Field(default="<:defconsettingsupdated:470326274082996224>")  # noqa: E704

    failmail: str = Field(default="<:failmail:633660039931887616>")

    incident_actioned: str = Field(default="<:incident_actioned:714221559279255583>")
    incident_investigating: str = Field(default="<:incident_investigating:714224190928191551>")
    incident_unactioned: str = Field(default="<:incident_unactioned:714223099645526026>")

    status_dnd: str = Field(default="<:status_dnd:470326272082313216>")
    status_idle: str = Field(default="<:status_idle:470326266625785866>")
    status_offline: str = Field(default="<:status_offline:470326266537705472>")
    status_online: str = Field(default="<:status_online:470326272351010816>")

    ducky_dave: str = Field(default="<:ducky_dave:742058418692423772>")

    trashcan: str = Field(default="<:trashcan:637136429717389331>")

    bullet: str = Field(default="\u2022")
    check_mark: str = Field(default="\u2705")
    cross_mark: str = Field(default="\u274C")
    new: str = Field(default="\U0001F195")
    pencil: str = Field(default="\u270F")

    ok_hand: str = Field(default=":ok_hand:")


Emojis = _Emojis()


class _Icons(EnvConfig):
    EnvConfig.Config.env_prefix = "icons__"

    crown_blurple: str = Field(default="https://cdn.discordapp.com/emojis/469964153289965568.png")
    crown_green: str = Field(default="https://cdn.discordapp.com/emojis/469964154719961088.png")
    crown_red: str = Field(default="https://cdn.discordapp.com/emojis/469964154879344640.png")

    defcon_denied: str = Field(default="https://cdn.discordapp.com/emojis/472475292078964738.png")    # noqa: E704
    defcon_shutdown: str = Field(default="https://cdn.discordapp.com/emojis/470326273952972810.png")  # noqa: E704
    defcon_unshutdown: str = Field(default="https://cdn.discordapp.com/emojis/470326274213150730.png")   # noqa: E704
    defcon_update: str = Field(default="https://cdn.discordapp.com/emojis/472472638342561793.png")   # noqa: E704

    filtering: str = Field(default="https://cdn.discordapp.com/emojis/472472638594482195.png")

    green_checkmark: str = Field(
        default="https://raw.githubusercontent.com/python-discord/branding/main/icons/checkmark/green-checkmark-dist.png"
    )
    green_questionmark: str = Field(
        default="https://raw.githubusercontent.com/python-discord/branding/main/icons/checkmark/green-question-mark-dist.png"
    )
    guild_update: str = Field(default="https://cdn.discordapp.com/emojis/469954765141442561.png")

    hash_blurple: str = Field(default="https://cdn.discordapp.com/emojis/469950142942806017.png")
    hash_green: str = Field(default="https://cdn.discordapp.com/emojis/469950144918585344.png")
    hash_red: str = Field(default="https://cdn.discordapp.com/emojis/469950145413251072.png")

    message_bulk_delete: str = Field(default="https://cdn.discordapp.com/emojis/469952898994929668.png")
    message_delete: str = Field(default="https://cdn.discordapp.com/emojis/472472641320648704.png")
    message_edit: str = Field(default="https://cdn.discordapp.com/emojis/472472638976163870.png")

    pencil: str = Field(default="https://cdn.discordapp.com/emojis/470326272401211415.png")

    questionmark: str = Field(default="https://cdn.discordapp.com/emojis/512367613339369475.png")

    remind_blurple: str = Field(default="https://cdn.discordapp.com/emojis/477907609215827968.png")
    remind_green: str = Field(default="https://cdn.discordapp.com/emojis/477907607785570310.png")
    remind_red: str = Field(default="https://cdn.discordapp.com/emojis/477907608057937930.png")

    sign_in: str = Field(default="https://cdn.discordapp.com/emojis/469952898181234698.png")
    sign_out: str = Field(default="https://cdn.discordapp.com/emojis/469952898089091082.png")

    superstarify: str = Field(default="https://cdn.discordapp.com/emojis/636288153044516874.png")
    unsuperstarify: str = Field(default="https://cdn.discordapp.com/emojis/636288201258172446.png")

    token_removed: str = Field(default="https://cdn.discordapp.com/emojis/470326273298792469.png")

    user_ban: str = Field(default="https://cdn.discordapp.com/emojis/469952898026045441.png")
    user_mute: str = Field(default="https://cdn.discordapp.com/emojis/472472640100106250.png")
    user_unban: str = Field(default="https://cdn.discordapp.com/emojis/469952898692808704.png")
    user_unmute: str = Field(default="https://cdn.discordapp.com/emojis/472472639206719508.png")
    user_update: str = Field(default="https://cdn.discordapp.com/emojis/469952898684551168.png")
    user_verified: str = Field(default="https://cdn.discordapp.com/emojis/470326274519334936.png")
    user_warn: str = Field(default="https://cdn.discordapp.com/emojis/470326274238447633.png")

    voice_state_blue: str = Field(default="https://cdn.discordapp.com/emojis/656899769662439456.png")
    voice_state_green: str = Field(default="https://cdn.discordapp.com/emojis/656899770094452754.png")
    voice_state_red: str = Field(default="https://cdn.discordapp.com/emojis/656899769905709076.png")


Icons = _Icons()


class _Filter(EnvConfig):
    EnvConfig.Config.env_prefix = "filters__"

    filter_domains: bool = Field(default=True)
    filter_everyone_ping: bool = Field(default=True)
    filter_invites: bool = Field(default=True)
    filter_zalgo: bool = Field(default=False)
    watch_regex: bool = Field(default=True)
    watch_rich_embeds: bool = Field(default=True)

    # Notifications are not expected for "watchlist" type filters

    notify_user_domains: bool = Field(default=False)
    notify_user_everyone_ping: bool = Field(default=True)
    notify_user_invites: bool = Field(default=True)
    notify_user_zalgo: bool = Field(default=False)

    offensive_msg_delete_days: int = Field(default=7)
    ping_everyone: bool = Field(default=True)

    channel_whitelist = [
        Channels.admins,
        Channels.big_brother_logs,
        Channels.dev_log,
        Channels.message_log,
        Channels.mod_log,
        Channels.staff_lounge
    ]
    role_whitelist = [
        Roles.admins,
        Roles.helpers,
        Roles.moderators,
        Roles.owners,
        Roles.python_community,
        Roles.sprinters,
        Roles.partners
    ]


Filter = _Filter()


class _Keys(EnvConfig):

    github = Field(default="", env="GITHUB_API_KEY")
    site_api = Field(default="", env="BOT_API_KEY")


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
