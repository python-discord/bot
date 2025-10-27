import base64
import logging
import os
import re
import sys
from pathlib import Path
from types import TracebackType
from typing import Any, Final, cast

from dotenv import load_dotenv
from httpx import Client, HTTPStatusError, Response

# Filter out the send typing monkeypatch logs from bot core when we import to get constants
logging.getLogger("pydis_core").setLevel(logging.WARNING)

from bot.constants import (  # noqa: E402
    Webhooks,
    _Categories,  # pyright: ignore[reportPrivateUsage]
    _Channels,  # pyright: ignore[reportPrivateUsage]
    _Emojis,  # pyright: ignore[reportPrivateUsage]
    _Roles,  # pyright: ignore[reportPrivateUsage]
)
from bot.log import get_logger  # noqa: E402

load_dotenv()
log = get_logger("botstrap")
# Silence noisy httpcore logger
get_logger("httpcore").setLevel("INFO")

ENV_FILE = Path(".env.server")
BOT_TOKEN = os.getenv("BOT_TOKEN", None)
GUILD_ID = os.getenv("GUILD_ID", None)

COMMUNITY_FEATURE = "COMMUNITY"
PYTHON_HELP_CHANNEL_NAME = "python_help"
PYTHON_HELP_CATEGORY_NAME = "python_help_system"
ANNOUNCEMENTS_CHANNEL_NAME = "announcements"
RULES_CHANNEL_NAME = "rules"
GUILD_CATEGORY_TYPE = 4
GUILD_FORUM_TYPE = 15
EMOJI_REGEX = re.compile(r"<:(\w+):(\d+)>")

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


class BotstrapError(Exception):
    """Raised when an error occurs during the botstrap process."""


class DiscordClient(Client):
    """An HTTP client to communicate with Discord's APIs."""

    CDN_BASE_URL: Final[str] = "https://cdn.discordapp.com"

    def __init__(self, guild_id: int | str):
        super().__init__(
            base_url="https://discord.com/api/v10",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
            event_hooks={"response": [self._raise_for_status]},
        )
        self.guild_id = guild_id
        self._app_info: dict[str, Any] | None = None
        self._guild_info: dict[str, Any] | None = None
        self._guild_channels: list[dict[str, Any]] | None = None

    @staticmethod
    def _raise_for_status(response: Response) -> None:
        response.raise_for_status()

    @property
    def guild_info(self) -> dict[str, Any]:
        """Fetches the guild's information."""
        if self._guild_info is None:
            response = self.get(f"/guilds/{self.guild_id}")
            self._guild_info = cast("dict[str, Any]", response.json())
        return self._guild_info

    @property
    def guild_channels(self) -> list[dict[str, Any]]:
        """Fetches the guild's channels."""
        if self._guild_channels is None:
            response = self.get(f"/guilds/{self.guild_id}/channels")
            self._guild_channels = cast("list[dict[str, Any]]", response.json())
        return self._guild_channels

    def get_channel(self, id_: int | str) -> dict[str, Any]:
        """Fetches a channel by its ID."""
        for channel in self.guild_channels:
            if channel["id"] == str(id_):
                return channel
        raise KeyError(f"Channel with ID {id_} not found.")

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

    def check_if_in_guild(self) -> bool:
        """Check if the bot is a member of the guild."""
        try:
            _ = self.guild_info
        except HTTPStatusError as e:
            if e.response.status_code == 403 or e.response.status_code == 404:
                return False
            raise
        return True

    def upgrade_server_to_community_if_necessary(
        self,
        rules_channel_id_: int | str,
        announcements_channel_id_: int | str,
    ) -> None:
        """Fetches server info & upgrades to COMMUNITY if necessary."""
        payload = self.guild_info

        if COMMUNITY_FEATURE not in payload["features"]:
            log.info("This server is currently not a community, upgrading.")
            payload["features"].append(COMMUNITY_FEATURE)
            payload["rules_channel_id"] = rules_channel_id_
            payload["public_updates_channel_id"] = announcements_channel_id_
            self._guild_info = self.patch(f"/guilds/{self.guild_id}", json=payload).json()
            log.info("Server %s has been successfully updated to a community.", self.guild_id)

    def create_forum_channel(self, channel_name_: str, category_id_: int | str | None = None) -> str:
        """Creates a new forum channel."""
        payload: dict[str, Any] = {"name": channel_name_, "type": GUILD_FORUM_TYPE}
        if category_id_:
            payload["parent_id"] = category_id_

        response = self.post(
            f"/guilds/{self.guild_id}/channels",
            json=payload,
            headers={"X-Audit-Log-Reason": "Creating forum channel as part of PyDis botstrap"},
        )
        forum_channel_id = response.json()["id"]
        log.info("New forum channel: %s has been successfully created.", channel_name_)
        return forum_channel_id

    def is_forum_channel(self, channel_id: str) -> bool:
        """A boolean that indicates if a channel is of type GUILD_FORUM."""
        return self.get_channel(channel_id)["type"] == GUILD_FORUM_TYPE

    def delete_channel(self, channel_id: str | int) -> None:
        """Delete a channel."""
        log.info("Channel python-help: %s is not a forum channel and will be replaced with one.", channel_id)
        self.delete(f"/channels/{channel_id}")

    def get_all_roles(self) -> dict[str, int]:
        """Fetches all the roles in a guild."""
        result = SilencedDict(name="Roles dictionary")

        roles = self.guild_info["roles"]

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

        for channel in self.guild_channels:
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

    def get_all_guild_webhooks(self) -> list[dict[str, Any]]:
        """Lists all the webhooks for the guild."""
        response = self.get(f"/guilds/{self.guild_id}/webhooks")
        return response.json()

    def create_webhook(self, name: str, channel_id_: int) -> str:
        """Creates a new webhook for a particular channel."""
        payload = {"name": name}

        response = self.post(
            f"/channels/{channel_id_}/webhooks",
            json=payload,
            headers={"X-Audit-Log-Reason": "Creating webhook as part of PyDis botstrap"},
        )
        new_webhook = response.json()
        return new_webhook["id"]

    def list_emojis(self) -> list[dict[str, Any]]:
        """Lists all the emojis for the guild."""
        response = self.get(f"/guilds/{self.guild_id}/emojis")
        return response.json()

    def get_emoji_contents(self, id_: str | int) -> bytes | None:
        """Fetches the image data for an emoji by ID."""
        # emojis are located at https://cdn.discordapp.com/emojis/{emoji_id}.{ext}
        response = self.get(f"{self.CDN_BASE_URL}/emojis/{id_!s}.webp")
        return response.content

    def clone_emoji(self, *, new_name: str, original_emoji_id: str | int) -> str:
        """Creates a new emoji in the guild, cloned from another emoji by ID."""
        emoji_data = self.get_emoji_contents(original_emoji_id)
        if not emoji_data:
            log.warning("Couldn't find emoji with ID %s.", original_emoji_id)
            return ""

        payload = {
            "name": new_name,
            "image": f"data:image/png;base64,{base64.b64encode(emoji_data).decode('utf-8')}",
        }

        response = self.post(
            f"/guilds/{self.guild_id}/emojis",
            json=payload,
            headers={"X-Audit-Log-Reason": f"Creating {new_name} emoji as part of PyDis botstrap"},
        )
        new_emoji = response.json()
        return new_emoji["id"]


class BotStrapper:
    """Bootstrap the bot configuration for a given guild."""

    def __init__(self, guild_id: int | str, env_file: Path):
        self.client = DiscordClient(guild_id=guild_id)
        self.env_file = env_file

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        self.client.__exit__(exc_type, exc_value, traceback)

    def upgrade_client(self) -> bool:
        """Upgrade the application's flags if necessary."""
        if self.client.upgrade_application_flags_if_necessary():
            log.info("Application flags upgraded successfully, and necessary intents are now enabled.")
            return True
        return False

    def check_guild_membership(self) -> None:
        """Check the bot is in the required guild."""
        if not self.client.check_if_in_guild():
            client_id = self.client.app_info["id"]
            log.error("The bot is not a member of the configured guild with ID %s.", GUILD_ID)
            log.warning(
                "Please invite with the following URL and rerun this script: "
                "https://discord.com/oauth2/authorize?client_id=%s&guild_id=%s&scope=bot+applications.commands&permissions=8",
                client_id,
                GUILD_ID,
            )
            raise BotstrapError("Bot is not a member of the configured guild.")

    def get_roles(self) -> dict[str, Any]:
        """Get a config map of all of the roles in the guild."""
        all_roles = self.client.get_all_roles()

        data: dict[str, int] = {}

        for role_name in _Roles.model_fields:
            role_id = all_roles.get(role_name, None)
            if not role_id:
                log.warning("Couldn't find the role %s in the guild, PyDis' default values will be used.", role_name)
                continue

            data[role_name] = role_id

        return data

    def get_channels(self) -> dict[str, Any]:
        """Get a config map of all of the channels in the guild."""
        all_channels, all_categories = self.client.get_all_channels_and_categories()

        rules_channel_id = all_channels[RULES_CHANNEL_NAME]
        announcements_channel_id = all_channels[ANNOUNCEMENTS_CHANNEL_NAME]

        self.client.upgrade_server_to_community_if_necessary(rules_channel_id, announcements_channel_id)

        if python_help_channel_id := all_channels.get(PYTHON_HELP_CHANNEL_NAME):
            if not self.client.is_forum_channel(python_help_channel_id):
                self.client.delete_channel(python_help_channel_id)
                python_help_channel_id = None

        if not python_help_channel_id:
            python_help_channel_name = PYTHON_HELP_CHANNEL_NAME.replace("_", "-")
            python_help_category_id = all_categories[PYTHON_HELP_CATEGORY_NAME]
            python_help_channel_id = self.client.create_forum_channel(python_help_channel_name, python_help_category_id)
            all_channels[PYTHON_HELP_CHANNEL_NAME] = python_help_channel_id

        data: dict[str, str] = {}
        for channel_name in _Channels.model_fields:
            channel_id = all_channels.get(channel_name, None)
            if not channel_id:
                log.warning(
                    "Couldn't find the channel %s in the guild, PyDis' default values will be used.", channel_name
                )
                continue

            data[channel_name] = channel_id

        return data

    def get_categories(self) -> dict[str, Any]:
        """Get a config map of all of the categories in guild."""
        _channels, all_categories = self.client.get_all_channels_and_categories()

        data: dict[str, str] = {}
        for category_name in _Categories.model_fields:
            category_id = all_categories.get(category_name, None)
            if not category_id:
                log.warning(
                    "Couldn't find the category %s in the guild, PyDis' default values will be used.", category_name
                )
                continue

            data[category_name] = category_id
        return data

    def sync_webhooks(self) -> dict[str, Any]:
        """Get webhook config. Will create all webhooks that cannot be found."""
        all_channels, _categories = self.client.get_all_channels_and_categories()

        data: dict[str, Any] = {}

        existing_webhooks = self.client.get_all_guild_webhooks()
        for webhook_name, webhook_model in Webhooks:
            formatted_webhook_name = webhook_name.replace("_", " ").title()
            for existing_hook in existing_webhooks:
                if (
                    # check the existing ID matches the configured one
                    existing_hook["id"] == str(webhook_model.id)
                    or (
                        # check if the name and the channel ID match the configured ones
                        existing_hook["name"] == formatted_webhook_name
                        and existing_hook["channel_id"] == str(all_channels[webhook_name])
                    )
                ):
                    webhook_id = existing_hook["id"]
                    break
            else:
                webhook_channel_id = int(all_channels[webhook_name])
                webhook_id = self.client.create_webhook(formatted_webhook_name, webhook_channel_id)

            data[webhook_name + "__id"] = webhook_id

        return data

    def sync_emojis(self) -> dict[str, Any]:
        """Get emoji config. Will create all emojis that cannot be found."""
        existing_emojis = self.client.list_emojis()
        log.debug("Syncing emojis with bot configuration.")
        data: dict[str, Any] = {}
        for emoji_config_name, emoji_config in _Emojis.model_fields.items():
            if not (match := EMOJI_REGEX.match(emoji_config.default)):
                continue
            emoji_name = match.group(1)
            emoji_id = match.group(2)

            for emoji in existing_emojis:
                if emoji["name"] == emoji_name:
                    emoji_id = emoji["id"]
                    break
            else:
                log.info("Creating emoji %s", emoji_name)
                emoji_id = self.client.clone_emoji(new_name=emoji_name, original_emoji_id=emoji_id)

            data[emoji_config_name] = f"<:{emoji_name}:{emoji_id}>"

        return data

    def write_config_env(self, config: dict[str, dict[str, Any]], env_file: Path) -> None:
        """Write the configuration to the specified env_file."""
        # in order to support commented sections, we write the following
        with self.env_file.open("wb") as file:
            # format the dictionary into .env style
            for category, category_values in config.items():
                file.write(f"# {category.capitalize()}\n".encode())
                for key, value in category_values.items():
                    file.write(f"{category}_{key}={value}\n".encode())
                file.write(b"\n")

    def run(self) -> None:
        """Runs the botstrap process."""
        config: dict[str, dict[str, Any]] = {}
        self.upgrade_client()
        self.check_guild_membership()
        config["categories"] = self.get_categories()
        config["channels"] = self.get_channels()
        config["roles"] = self.get_roles()

        config["webhooks"] = self.sync_webhooks()
        config["emojis"] = self.sync_emojis()

        self.write_config_env(config, self.env_file)


if __name__ == "__main__":
    botstrap = BotStrapper(guild_id=GUILD_ID, env_file=ENV_FILE)
    with botstrap:
        botstrap.run()
    log.info("Botstrap completed successfully. Configuration has been written to %s", ENV_FILE)
