import re

INVITE_RE = re.compile(
    r"(discord([\.,]|dot)gg|"                     # Could be discord.gg/
    r"discord([\.,]|dot)com(\/|slash)invite|"     # or discord.com/invite/
    r"discordapp([\.,]|dot)com(\/|slash)invite|"  # or discordapp.com/invite/
    r"discord([\.,]|dot)me|"                      # or discord.me
    r"discord([\.,]|dot)li|"                      # or discord.li
    r"discord([\.,]|dot)io|"                      # or discord.io.
    r"((?<!\w)([\.,]|dot))gg"                     # or .gg/
    r")([\/]|slash)"                              # / or 'slash'
    r"(?P<invite>[a-zA-Z0-9\-]+)",                # the invite code itself
    flags=re.IGNORECASE
)

MESSAGE_ID_RE = re.compile(r'(?P<message_id>[0-9]{15,20})$')

DISCORD_MESSAGE_LINK_RE = re.compile(
    r"(https?:\/\/(?:(ptb|canary|www)\.)?discord(?:app)?\.com\/channels\/"
    r"[0-9]{15,20}"
    r"\/[0-9]{15,20}\/[0-9]{15,20})"
)
