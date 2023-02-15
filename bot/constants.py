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
from pathlib import Path


from pydantic import BaseSettings, BaseModel

# Will add a check for the required keys

env_file_path = Path(__file__).parent.parent / ".env"
server_env_file_path = Path(__file__).parent.parent / ".env.server"

FILE_LOGS = True
DEBUG_MODE = True


class EnvConfig(BaseSettings):
    class Config:
        env_file = env_file_path, server_env_file_path
        env_file_encoding = 'utf-8'


class _Bot(EnvConfig):
    EnvConfig.Config.env_prefix = "bot__"

    prefix: str
    sentry_dsn: str | None
    token: str
    trace_loggers: str = "*"


class _Channels(EnvConfig):
    EnvConfig.Config.env_prefix = "channels__"
    bot_commands: int


class _Roles(EnvConfig):

    EnvConfig.Config.env_prefix = "roles__"
    advent_of_code: int
    announcements: int


class _Guild(BaseSettings):
    id: int
    roles: _Roles


Bot = _Bot()

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
