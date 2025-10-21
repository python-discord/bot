import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv
from httpx import Client, HTTPStatusError, Response

# Filter out the send typing monkeypatch logs from bot core when we import to get constants
logging.getLogger("pydis_core").setLevel(logging.WARNING)

from bot.constants import (  # noqa: E402
    Webhooks,
    _Categories,  # pyright: ignore[reportPrivateUsage]
    _Channels,  # pyright: ignore[reportPrivateUsage]
    _Roles,  # pyright: ignore[reportPrivateUsage]
)
from bot.log import get_logger  # noqa: E402

load_dotenv()
log = get_logger("botstrap")
# Silence noisy httpcore logger
get_logger("httpcore").setLevel("INFO")

env_file_path = Path(".env.server")
BOT_TOKEN = os.getenv("BOT_TOKEN", None)
GUILD_ID = os.getenv("GUILD_ID", None)

COMMUNITY_FEATURE = "COMMUNITY"
PYTHON_HELP_CHANNEL_NAME = "python_help"
PYTHON_HELP_CATEGORY_NAME = "python_help_system"
ANNOUNCEMENTS_CHANNEL_NAME = "announcements"
RULES_CHANNEL_NAME = "rules"
GUILD_CATEGORY_TYPE = 4
GUILD_FORUM_TYPE = 15

if not BOT_TOKEN:
    message = (
        "Couldn't find the `BOT_TOKEN` environment variable. "
        "Make sure to add it to your `.env` file like this: `BOT_TOKEN=value_of_your_bot_token`"
    )
    log.warning(message)
    raise ValueError(message)

if not GUILD_ID:
    message = (
        "Couldn't find the `GUILD_ID` environment variable. "
        "Make sure to add it to your `.env` file like this: `GUILD_ID=value_of_your_discord_server_id`"
    )
    log.warning(message)
    raise ValueError(message)


class SilencedDict(dict[str, Any]):
    """A dictionary that silences KeyError exceptions upon subscription to non existent items."""

    def __init__(self, name: str):
        self.name = name
        super().__init__()

    def __getitem__(self, item: str):
        try:
            return super().__getitem__(item)
        except KeyError:
            log.fatal("Couldn't find key: %s in dict: %s", item, self.name)
            log.warning(
                "Please follow our contribution guidelines "
                "https://pydis.com/contributing-bot "
                "to guarantee a successful run of botstrap "
            )
            sys.exit(-1)


class DiscordClient(Client):
    """An HTTP client to communicate with Discord's APIs."""

    def __init__(self, guild_id: int | str):
        super().__init__(
            base_url="https://discord.com/api/v10",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
            event_hooks={"response": [self._raise_for_status]},
        )
        self.guild_id = guild_id
        self._app_info: dict[str, Any] | None = None

    @staticmethod
    def _raise_for_status(response: Response) -> None:
        response.raise_for_status()

    @property
    def app_info(self) -> dict[str, Any]:
        """Fetches the application's information."""
        if self._app_info is None:
            response = self.get("/applications/@me")
            self._app_info = cast("dict[str, Any]", response.json())
        return self._app_info

    def upgrade_application_flags_if_necessary(self) -> bool:
        """
        Set the app's flags to allow the intents that we need.

        Returns a boolean defining whether changes were made.
        """
        # Fetch first to modify, not overwrite
        current_flags = self.app_info.get("flags", 0)
        new_flags = current_flags | 1 << 15 | 1 << 19

        if new_flags != current_flags:
            resp = self.patch("/applications/@me", json={"flags": new_flags})
            self._app_info = cast("dict[str, Any]", resp.json())
            return True

        return False

    def upgrade_server_to_community_if_necessary(
        self,
        rules_channel_id_: int | str,
        announcements_channel_id_: int | str,
    ) -> None:
        """Fetches server info & upgrades to COMMUNITY if necessary."""
        response = self.get(f"/guilds/{self.guild_id}")
        payload = response.json()

        if COMMUNITY_FEATURE not in payload["features"]:
            log.info("This server is currently not a community, upgrading.")
            payload["features"].append(COMMUNITY_FEATURE)
            payload["rules_channel_id"] = rules_channel_id_
            payload["public_updates_channel_id"] = announcements_channel_id_
            self.patch(f"/guilds/{self.guild_id}", json=payload)
            log.info(f"Server {self.guild_id} has been successfully updated to a community.")

    def create_forum_channel(self, channel_name_: str, category_id_: int | str | None = None) -> str:
        """Creates a new forum channel."""
        payload: dict[str, Any] = {"name": channel_name_, "type": GUILD_FORUM_TYPE}
        if category_id_:
            payload["parent_id"] = category_id_

        response = self.post(f"/guilds/{self.guild_id}/channels", json=payload)
        forum_channel_id = response.json()["id"]
        log.info(f"New forum channel: {channel_name_} has been successfully created.")
        return forum_channel_id

    def is_forum_channel(self, channel_id_: str) -> bool:
        """A boolean that indicates if a channel is of type GUILD_FORUM."""
        response = self.get(f"/channels/{channel_id_}")
        return response.json()["type"] == GUILD_FORUM_TYPE

    def delete_channel(self, channel_id_: str | int) -> None:
        """Delete a channel."""
        log.info(f"Channel python-help: {channel_id_} is not a forum channel and will be replaced with one.")
        self.delete(f"/channels/{channel_id_}")

    def get_all_roles(self) -> dict[str, int]:
        """Fetches all the roles in a guild."""
        result = SilencedDict(name="Roles dictionary")

        response = self.get(f"guilds/{self.guild_id}/roles")
        roles = response.json()

        for role in roles:
            name = "_".join(part.lower() for part in role["name"].split(" ")).replace("-", "_")
            result[name] = role["id"]

        return result

    def get_all_channels_and_categories(self) -> tuple[dict[str, str], dict[str, str]]:
        """Fetches all the text channels & categories in a guild."""
        off_topic_channel_name_regex = r"ot\d{1}(_.*)+"
        off_topic_count = 0
        channels = SilencedDict(name="Channels dictionary")
        categories = SilencedDict(name="Categories dictionary")

        response = self.get(f"guilds/{self.guild_id}/channels")
        server_channels = response.json()

        for channel in server_channels:
            channel_type = channel["type"]
            name = "_".join(part.lower() for part in channel["name"].split(" ")).replace("-", "_")
            if re.match(off_topic_channel_name_regex, name):
                name = f"off_topic_{off_topic_count}"
                off_topic_count += 1

            if channel_type == GUILD_CATEGORY_TYPE:
                categories[name] = channel["id"]
            else:
                channels[name] = channel["id"]

        return channels, categories

    def webhook_exists(self, webhook_id_: int) -> bool:
        """A predicate that indicates whether a webhook exists already or not."""
        try:
            self.get(f"/webhooks/{webhook_id_}")
            return True
        except HTTPStatusError:
            return False

    def create_webhook(self, name: str, channel_id_: int) -> str:
        """Creates a new webhook for a particular channel."""
        payload = {"name": name}

        response = self.post(f"/channels/{channel_id_}/webhooks", json=payload)
        new_webhook = response.json()
        return new_webhook["id"]


with DiscordClient(guild_id=GUILD_ID) as discord_client:
    if discord_client.upgrade_application_flags_if_necessary():
        log.info("Application flags upgraded successfully, and necessary intents are now enabled.")

    config_str = "#Roles\n"

    all_roles = discord_client.get_all_roles()

    for role_name in _Roles.model_fields:
        role_id = all_roles.get(role_name, None)
        if not role_id:
            log.warning("Couldn't find the role %s in the guild, PyDis' default values will be used.", role_name)
            continue

        config_str += f"roles_{role_name}={role_id}\n"

    all_channels, all_categories = discord_client.get_all_channels_and_categories()

    config_str += "\n#Channels\n"

    rules_channel_id = all_channels[RULES_CHANNEL_NAME]
    announcements_channel_id = all_channels[ANNOUNCEMENTS_CHANNEL_NAME]

    discord_client.upgrade_server_to_community_if_necessary(rules_channel_id, announcements_channel_id)

    if python_help_channel_id := all_channels.get(PYTHON_HELP_CHANNEL_NAME):
        if not discord_client.is_forum_channel(python_help_channel_id):
            discord_client.delete_channel(python_help_channel_id)
            python_help_channel_id = None

    if not python_help_channel_id:
        python_help_channel_name = PYTHON_HELP_CHANNEL_NAME.replace("_", "-")
        python_help_category_id = all_categories[PYTHON_HELP_CATEGORY_NAME]
        python_help_channel_id = discord_client.create_forum_channel(python_help_channel_name, python_help_category_id)
        all_channels[PYTHON_HELP_CHANNEL_NAME] = python_help_channel_id

    for channel_name in _Channels.model_fields:
        channel_id = all_channels.get(channel_name, None)
        if not channel_id:
            log.warning("Couldn't find the channel %s in the guild, PyDis' default values will be used.", channel_name)
            continue

        config_str += f"channels_{channel_name}={channel_id}\n"
    config_str += f"channels_{PYTHON_HELP_CHANNEL_NAME}={python_help_channel_id}\n"

    config_str += "\n#Categories\n"

    for category_name in _Categories.model_fields:
        category_id = all_categories.get(category_name, None)
        if not category_id:
            log.warning(
                "Couldn't find the category %s in the guild, PyDis' default values will be used.", category_name
            )
            continue

        config_str += f"categories_{category_name}={category_id}\n"

    env_file_path.write_text(config_str)

    config_str += "\n#Webhooks\n"

    for webhook_name, webhook_model in Webhooks:
        webhook = discord_client.webhook_exists(webhook_model.id)
        if not webhook:
            webhook_channel_id = int(all_channels[webhook_name])
            webhook_id = discord_client.create_webhook(webhook_name, webhook_channel_id)
        else:
            webhook_id = webhook_model.id
        config_str += f"webhooks_{webhook_name}__id={webhook_id}\n"
        config_str += f"webhooks_{webhook_name}__channel={all_channels[webhook_name]}\n"

    config_str += "\n#Emojis\n"
    config_str += "emojis_trashcan=🗑️"

    with env_file_path.open("wb") as file:
        file.write(config_str.encode("utf-8"))

    log.info("Botstrap completed successfully. Configuration has been written to %s", env_file_path)
