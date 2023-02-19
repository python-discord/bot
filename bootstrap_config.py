import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from bot.constants import _Categories, _Channels, _Roles, _Webhooks
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
    r = requests.get(url=roles_url, headers=headers)
    roles = r.json()

    for role in roles:
        name = "_".join(part.lower() for part in role["name"].split(" ")).replace("-", "_")
        result[name] = role["id"]

    return result


def get_all_channels_and_categories() -> (dict, dict):
    """Fetches all the text channels & categories in a guild."""
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


def get_channel_webhooks(channel_id_: int) -> dict:
    """Fetches webhooks of a particular channel."""
    result = {}
    webhooks_url = f"{base_url}/channels/{channel_id_}/webhooks"
    r = requests.get(url=webhooks_url, headers=headers)
    webhooks = r.json()

    for webhook in webhooks:
        name = "_".join(part.lower() for part in webhook["name"].split(" ")).replace("-", "_")
        result[name] = webhook["id"]

    return result


def create_webhook(name: str, channel_id_: int) -> tuple[int, str]:
    """Creates a new webhook for a particular channel."""
    create_webhook_url = f"{base_url}/channels/{channel_id_}/webhooks"
    payload = {"name": name}

    r = requests.post(url=create_webhook_url, headers=headers, json=payload)
    new_webhook = r.json()
    webhook_id_ = new_webhook["id"]
    webhook_token = new_webhook["token"]
    webhook_url = f"https://discord.com/api/webhooks/{webhook_id_}/{webhook_token}"

    return webhook_id_, webhook_url


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

Webhooks = _Webhooks()

for webhook_name, webhook_model in Webhooks:
    channel_webhooks = get_channel_webhooks(webhook_model.channel)
    webhook_ids = [int(id) for id in channel_webhooks.values()]
    if webhook_model.id in webhook_ids:
        log.info(f"Webhook {webhook_name} already exists, skipping.")
        continue

    webhook_id, webhook_url = create_webhook(f"{webhook_name}-testo", webhook_model.channel)
    config_str += f"webhooks__{webhook_name}__id={webhook_id}\n"
    config_str += f"webhooks__{webhook_name}__channel={webhook_model.channel}\n"
    config_str += f"webhooks__{webhook_name}__url={webhook_url}\n"

env_file_path.write_text(config_str)
