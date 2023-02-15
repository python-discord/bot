from pathlib import Path
import requests
from bot.constants import _Roles, _Channels, _Categories

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
    channels = {} # could be text channels only as well
    categories = {}
    channels_url = f"{base_url}/guilds/{guild_id}/channels"
    r = requests.get(url=channels_url, headers=headers)
    all_channels = r.json()

    for channel in all_channels:
        channel_type = channel["type"]
        name = "_".join(part.lower() for part in channel["name"].split(" ")).replace("-", "_")
        if channel_type == 4:
            categories[name] = channel["id"]
        else:
            channels[name] = channel["id"]

    return channels, categories


config_str = ""

all_roles = get_all_roles()

for role_name in _Roles.__fields__:
    config_str += f"roles__{role_name}={all_roles.get(role_name)}\n"

all_channels, all_categories = get_all_channels_and_categories()

for channel_name in _Channels.__fields__:
    config_str += f"channels__{channel_name}={all_channels.get(channel_name)}\n"

for category_name in _Categories.__fields__:
    config_str += f"categories__{category_name}={all_categories.get(category_name)}\n"

env_file_path.write_text(config_str)