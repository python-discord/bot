import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from bot.constants import Webhooks, _Categories, _Channels, _Roles
from bot.log import get_logger

load_dotenv()
log = get_logger("Config Bootstrapper")

env_file_path = Path(".env.server")
token = os.getenv("BOT_TOKEN", None)
guild_id = os.getenv("GUILD_ID", None)


if not token:
    message = (
        "Couldn't find BOT_TOKEN in the environment variables."
        "Make sure to add it to the `.env` file likewise: `BOT_TOKEN=value_of_your_bot_token`"
    )
    log.warning(message)
    raise ValueError(message)

if not guild_id:
    message = (
        "Couldn't find GUILD_ID in the environment variables."
        "Make sure to add it to the `.env` file likewise: `GUILD_ID=value_of_your_discord_server_id`"
    )
    log.warning(message)
    raise ValueError(message)


base_url = "https://discord.com/api/v10"

headers = {"Authorization": f"Bot {token}"}


def get_all_roles() -> dict:
    """Fetches all the roles in a guild."""
    result = {}

    roles_url = f"{base_url}/guilds/{guild_id}/roles"
    response = requests.get(url=roles_url, headers=headers)
    roles = response.json()

    for role in roles:
        name = "_".join(part.lower() for part in role["name"].split(" ")).replace("-", "_")
        result[name] = role["id"]

    return result


def get_all_channels_and_categories() -> tuple[dict[str, str], dict[str, str]]:
    """Fetches all the text channels & categories in a guild."""
    channels = {}  # could be text channels only as well
    categories = {}
    channels_url = f"{base_url}/guilds/{guild_id}/channels"

    response = requests.get(url=channels_url, headers=headers)
    server_channels = response.json()

    for channel in server_channels:
        channel_type = channel["type"]
        name = "_".join(part.lower() for part in channel["name"].split(" ")).replace("-", "_")
        if channel_type == 4:
            categories[name] = channel["id"]
        else:
            channels[name] = channel["id"]

    return channels, categories


def get_webhook(webhook_id_: int) -> dict:
    """Fetches a particular webhook by its id."""
    webhooks_url = f"{base_url}/webhooks/{webhook_id_}"
    response = requests.get(url=webhooks_url, headers=headers)
    if response.status_code == 200:
        return response.json()

    return {}


def create_webhook(name: str, channel_id_: int) -> str:
    """Creates a new webhook for a particular channel."""
    create_webhook_url = f"{base_url}/channels/{channel_id_}/webhooks"
    payload = {"name": name}

    response = requests.post(url=create_webhook_url, headers=headers, json=payload)
    new_webhook = response.json()
    return new_webhook["id"]


config_str = "#Roles\n"

all_roles = get_all_roles()

for role_name in _Roles.__fields__:

    role_id = all_roles.get(role_name, None)
    if not role_id:
        log.warning(f"Couldn't find the role {role_name} in the guild, PyDis' default values will be used.")
        continue

    config_str += f"roles__{role_name}={role_id}\n"

all_channels, all_categories = get_all_channels_and_categories()

config_str += "\n#Channels\n"


for channel_name in _Channels.__fields__:
    channel_id = all_channels.get(channel_name, None)
    if not channel_id:
        log.warning(f"Couldn't find the channel {channel_name} in the guild, PyDis' default values will be used.")
        continue

    config_str += f"channels__{channel_name}={channel_id}\n"

config_str += "\n#Categories\n"

for category_name in _Categories.__fields__:
    category_id = all_categories.get(category_name, None)
    if not category_id:
        log.warning(f"Couldn't find the category {category_name} in the guild, PyDis' default values will be used.")
        continue

    config_str += f"categories__{category_name}={category_id}\n"


env_file_path.write_text(config_str)

config_str += "\n#Webhooks\n"


for webhook_name, webhook_model in Webhooks:
    webhook = get_webhook(webhook_model.id)
    if not webhook:
        webhook_id = create_webhook(webhook_name, webhook_model.channel)
    else:
        webhook_id = webhook["id"]
    config_str += f"webhooks__{webhook_name}__id={webhook_id}\n"
    config_str += f"webhooks__{webhook_name}__channel={webhook_model.channel}\n"

env_file_path.write_text(config_str)
