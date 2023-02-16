from pathlib import Path
import requests
from bot.constants import _Roles, _Channels, _Categories

from bot.log import get_logger

log = get_logger(__name__)


env_file_path = Path(".env.server")

token = "my_precious_token"  #Replace this with bot's token
guild_id = 999999999999999999  #Replace this with target guild id


base_url = "https://discord.com/api/v10"

headers = {"Authorization": f"Bot {token}"}


def get_all_roles():
    result = {}

    roles_url = f"{base_url}/guilds/{guild_id}/roles"
    r = requests.get(url=roles_url, headers=headers)
    roles = r.json()

    for role in roles:
        try:
            name = "_".join(part.lower() for part in role["name"].split(" "))
            result[name] = role["id"]
        except Exception as e:
            pass

    return result


def get_all_channels_and_categories():
    channels = {}  # could be text channels only as well
    categories = {}
    channels_url = f"{base_url}/guilds/{guild_id}/channels"

    r = requests.get(url=channels_url, headers=headers)
    server_channels = r.json()

    for channel in server_channels:
        channel_type = channel["type"]
        name = "_".join(part.lower() for part in channel["name"].split(" ")).replace("-", "_")
        if channel_type == 4:
            categories[name] = channel["id"]
        else:
            channels[name] = channel["id"]

    return channels, categories


config_str = "#Roles\n"

all_roles = get_all_roles()

for role_name in _Roles.__fields__:

    role_id = all_roles.get(role_name, None)
    if not role_id:
        log.warning(f"Couldn't find the role {role_name} in the server")
        continue

    config_str += f"roles__{role_name}={role_id}\n"

all_channels, all_categories = get_all_channels_and_categories()

config_str += "\n#Channels\n"

for channel_name in _Channels.__fields__:
    channel_id = all_channels.get(channel_name, None)
    if not channel_id:
        log.warning(f"Couldn't find the channel {channel_name} in the server")
        continue

    config_str += f"channels__{channel_name}={channel_id}\n"

config_str += "\n#Categories\n"

for category_name in _Categories.__fields__:
    category_id = all_categories.get(category_name, None)
    if not category_id:
        log.warning(f"Couldn't find the category {category_name} in the server")
        continue

    config_str += f"categories__{category_name}={category_id}\n"

env_file_path.write_text(config_str)