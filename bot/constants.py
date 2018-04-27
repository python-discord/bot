import os

# Server
PYTHON_GUILD = 267624335836053506

# Channels
BOT_CHANNEL = 267659945086812160
CHECKPOINT_TEST_CHANNEL = 422077681434099723
DEVLOG_CHANNEL = 409308876241108992
DEVTEST_CHANNEL = 414574275865870337
HELP1_CHANNEL = 303906576991780866
HELP2_CHANNEL = 303906556754395136
HELP3_CHANNEL = 303906514266226689
MOD_LOG_CHANNEL = 282638479504965634
PYTHON_CHANNEL = 267624335836053506
VERIFICATION_CHANNEL = 352442727016693763

# Roles
ADMIN_ROLE = 267628507062992896
MODERATOR_ROLE = 267629731250176001
VERIFIED_ROLE = 352427296948486144
OWNER_ROLE = 267627879762755584
DEVOPS_ROLE = 409416496733880320
CONTRIBUTOR_ROLE = 295488872404484098

# Clickup
CLICKUP_KEY = os.environ.get("CLICKUP_KEY")
CLICKUP_SPACE = 757069
CLICKUP_TEAM = 754996

# URLs
DEPLOY_URL = os.environ.get("DEPLOY_URL")
STATUS_URL = os.environ.get("STATUS_URL")
SITE_URL = os.environ.get("SITE_URL", "pythondiscord.local:8080")
SITE_PROTOCOL = 'http' if 'local' in SITE_URL else 'https'
SITE_API_URL = f"{SITE_PROTOCOL}://api.{SITE_URL}"
SITE_API_USER_URL = f"{SITE_API_URL}/user"
SITE_API_TAGS_URL = f"{SITE_API_URL}/tags"
SITE_API_HIPHOPIFY_URL = f"{SITE_API_URL}/hiphopify"
GITHUB_URL_BOT = "https://github.com/discord-python/bot"
BOT_AVATAR_URL = "https://raw.githubusercontent.com/discord-python/branding/master/logos/logo_circle/logo_circle.png"

# Keys
DEPLOY_BOT_KEY = os.environ.get("DEPLOY_BOT_KEY")
DEPLOY_SITE_KEY = os.environ.get("DEPLOY_SITE_KEY")
SITE_API_KEY = os.environ.get("BOT_API_KEY")

# Bot internals
HELP_PREFIX = "bot."
TAG_COOLDOWN = 60  # Per channel, per tag

# There are Emoji objects, but they're not usable until the bot is connected,
# so we're using string constants instead
GREEN_CHEVRON = "<:greenchevron:418104310329769993>"
RED_CHEVRON = "<:redchevron:418112778184818698>"
WHITE_CHEVRON = "<:whitechevron:418110396973711363>"

# PaperTrail logging
PAPERTRAIL_ADDRESS = os.environ.get("PAPERTRAIL_ADDRESS") or None
PAPERTRAIL_PORT = int(os.environ.get("PAPERTRAIL_PORT") or 0)

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
    "NEGATORY."
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
    "I'll allow it."
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
    "Noooooo!!"
]
