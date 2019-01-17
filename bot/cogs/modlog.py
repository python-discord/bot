import asyncio
import datetime
import logging
from typing import List, Optional, Union

from aiohttp import ClientResponseError
from dateutil.relativedelta import relativedelta
from deepdiff import DeepDiff
from discord import (
    CategoryChannel, Colour, Embed, File, Guild,
    Member, Message, NotFound, RawBulkMessageDeleteEvent,
    RawMessageDeleteEvent, RawMessageUpdateEvent, Role,
    TextChannel, User, VoiceChannel
)
from discord.abc import GuildChannel
from discord.ext.commands import Bot

from bot.constants import (
    Channels, Colours, Emojis,
    Event, Guild as GuildConstant, Icons,
    Keys, Roles, URLs
)
from bot.utils.time import humanize_delta

log = logging.getLogger(__name__)

GUILD_CHANNEL = Union[CategoryChannel, TextChannel, VoiceChannel]

CHANNEL_CHANGES_UNSUPPORTED = ("permissions",)
CHANNEL_CHANGES_SUPPRESSED = ("_overwrites", "position")
MEMBER_CHANGES_SUPPRESSED = ("activity", "status")
ROLE_CHANGES_UNSUPPORTED = ("colour", "permissions")


class ModLog:
    """
    Logging for server events and staff actions
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}
        self._ignored = {event: [] for event in Event}

        self._cached_deletes = []
        self._cached_edits = []

    async def upload_log(self, messages: List[Message]) -> Optional[str]:
        """
        Uploads the log data to the database via
        an API endpoint for uploading logs.

        Used in several mod log embeds.

        Returns a URL that can be used to view the log.
        """

        log_data = []

        for message in messages:
            author = f"{message.author.name}#{message.author.discriminator}"

            # message.author may return either a User or a Member. Users don't have roles.
            if type(message.author) is User:
                role_id = Roles.developer
            else:
                role_id = message.author.top_role.id

            content = message.content
            embeds = [embed.to_dict() for embed in message.embeds]
            attachments = ["<Attachment>" for _ in message.attachments]

            log_data.append({
                "content": content,
                "author": author,
                "user_id": str(message.author.id),
                "role_id": str(role_id),
                "timestamp": message.created_at.strftime("%D %H:%M"),
                "attachments": attachments,
                "embeds": embeds,
            })

        response = await self.bot.http_session.post(
            URLs.site_logs_api,
            headers=self.headers,
            json={"log_data": log_data}
        )

        try:
            data = await response.json()
            log_id = data["log_id"]
        except (KeyError, ClientResponseError):
            log.debug(
                "API returned an unexpected result:\n"
                f"{response.text}"
            )
            return

        return f"{URLs.site_logs_view}/{log_id}"

    def ignore(self, event: Event, *items: int):
        for item in items:
            if item not in self._ignored[event]:
                self._ignored[event].append(item)

    async def send_log_message(
            self,
            icon_url: Optional[str],
            colour: Colour,
            title: Optional[str],
            text: str,
            thumbnail: Optional[str] = None,
            channel_id: int = Channels.modlog,
            ping_everyone: bool = False,
            files: Optional[List[File]] = None,
            content: Optional[str] = None,
            additional_embeds: Optional[List[Embed]] = None,
            timestamp_override: Optional[datetime.datetime] = None,
            footer: Optional[str] = None,
    ):
        embed = Embed(description=text)

        if title and icon_url:
            embed.set_author(name=title, icon_url=icon_url)

        embed.colour = colour

        embed.timestamp = timestamp_override or datetime.datetime.utcnow()

        if footer:
            embed.set_footer(text=footer)

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        if ping_everyone:
            if content:
                content = f"@everyone\n{content}"
            else:
                content = "@everyone"

        channel = self.bot.get_channel(channel_id)
        log_message = await channel.send(content=content, embed=embed, files=files)

        if additional_embeds:
            await channel.send("With the following embed(s):")
            for additional_embed in additional_embeds:
                await channel.send(embed=additional_embed)

        return await self.bot.get_context(log_message)  # Optionally return for use with antispam

    async def on_guild_channel_create(self, channel: GUILD_CHANNEL):
        if channel.guild.id != GuildConstant.id:
            return

        if isinstance(channel, CategoryChannel):
            title = "Category created"
            message = f"{channel.name} (`{channel.id}`)"
        elif isinstance(channel, VoiceChannel):
            title = "Voice channel created"

            if channel.category:
                message = f"{channel.category}/{channel.name} (`{channel.id}`)"
            else:
                message = f"{channel.name} (`{channel.id}`)"
        else:
            title = "Text channel created"

            if channel.category:
                message = f"{channel.category}/{channel.name} (`{channel.id}`)"
            else:
                message = f"{channel.name} (`{channel.id}`)"

        await self.send_log_message(Icons.hash_green, Colour(Colours.soft_green), title, message)

    async def on_guild_channel_delete(self, channel: GUILD_CHANNEL):
        if channel.guild.id != GuildConstant.id:
            return

        if isinstance(channel, CategoryChannel):
            title = "Category deleted"
        elif isinstance(channel, VoiceChannel):
            title = "Voice channel deleted"
        else:
            title = "Text channel deleted"

        if channel.category and not isinstance(channel, CategoryChannel):
            message = f"{channel.category}/{channel.name} (`{channel.id}`)"
        else:
            message = f"{channel.name} (`{channel.id}`)"

        await self.send_log_message(
            Icons.hash_red, Colour(Colours.soft_red),
            title, message
        )

    async def on_guild_channel_update(self, before: GUILD_CHANNEL, after: GuildChannel):
        if before.guild.id != GuildConstant.id:
            return

        if before.id in self._ignored[Event.guild_channel_update]:
            self._ignored[Event.guild_channel_update].remove(before.id)
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done or key in CHANNEL_CHANGES_SUPPRESSED:
                continue

            if key in CHANNEL_CHANGES_UNSUPPORTED:
                changes.append(f"**{key.title()}** updated")
            else:
                new = value["new_value"]
                old = value["old_value"]

                changes.append(f"**{key.title()}:** `{old}` **->** `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{Emojis.bullet} {item}\n"

        if after.category:
            message = f"**{after.category}/#{after.name} (`{after.id}`)**\n{message}"
        else:
            message = f"**#{after.name}** (`{after.id}`)\n{message}"

        await self.send_log_message(
            Icons.hash_blurple, Colour.blurple(),
            "Channel updated", message
        )

    async def on_guild_role_create(self, role: Role):
        if role.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.crown_green, Colour(Colours.soft_green),
            "Role created", f"`{role.id}`"
        )

    async def on_guild_role_delete(self, role: Role):
        if role.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.crown_red, Colour(Colours.soft_red),
            "Role removed", f"{role.name} (`{role.id}`)"
        )

    async def on_guild_role_update(self, before: Role, after: Role):
        if before.guild.id != GuildConstant.id:
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done or key == "color":
                continue

            if key in ROLE_CHANGES_UNSUPPORTED:
                changes.append(f"**{key.title()}** updated")
            else:
                new = value["new_value"]
                old = value["old_value"]

                changes.append(f"**{key.title()}:** `{old}` **->** `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{Emojis.bullet} {item}\n"

        message = f"**{after.name}** (`{after.id}`)\n{message}"

        await self.send_log_message(
            Icons.crown_blurple, Colour.blurple(),
            "Role updated", message
        )

    async def on_guild_update(self, before: Guild, after: Guild):
        if before.id != GuildConstant.id:
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = diff.get("values_changed", {})
        diff_values.update(diff.get("type_changes", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done:
                continue

            new = value["new_value"]
            old = value["old_value"]

            changes.append(f"**{key.title()}:** `{old}` **->** `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{Emojis.bullet} {item}\n"

        message = f"**{after.name}** (`{after.id}`)\n{message}"

        await self.send_log_message(
            Icons.guild_update, Colour.blurple(),
            "Guild updated", message,
            thumbnail=after.icon_url_as(format="png")
        )

    async def on_member_ban(self, guild: Guild, member: Union[Member, User]):
        if guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_ban]:
            self._ignored[Event.member_ban].remove(member.id)
            return

        await self.send_log_message(
            Icons.user_ban, Colour(Colours.soft_red),
            "User banned", f"{member.name}#{member.discriminator} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png"),
            channel_id=Channels.modlog
        )

    async def on_member_join(self, member: Member):
        if member.guild.id != GuildConstant.id:
            return

        message = f"{member.name}#{member.discriminator} (`{member.id}`)"
        now = datetime.datetime.utcnow()
        difference = abs(relativedelta(now, member.created_at))

        message += "\n\n**Account age:** " + humanize_delta(difference)

        if difference.days < 1 and difference.months < 1 and difference.years < 1:  # New user account!
            message = f"{Emojis.new} {message}"

        await self.send_log_message(
            Icons.sign_in, Colour(Colours.soft_green),
            "User joined", message,
            thumbnail=member.avatar_url_as(static_format="png"),
            channel_id=Channels.userlog
        )

    async def on_member_remove(self, member: Member):
        if member.guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_remove]:
            self._ignored[Event.member_remove].remove(member.id)
            return

        await self.send_log_message(
            Icons.sign_out, Colour(Colours.soft_red),
            "User left", f"{member.name}#{member.discriminator} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png"),
            channel_id=Channels.userlog
        )

    async def on_member_unban(self, guild: Guild, member: User):
        if guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_unban]:
            self._ignored[Event.member_unban].remove(member.id)
            return

        await self.send_log_message(
            Icons.user_unban, Colour.blurple(),
            "User unbanned", f"{member.name}#{member.discriminator} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png"),
            channel_id=Channels.modlog
        )

    async def on_member_update(self, before: Member, after: Member):
        if before.guild.id != GuildConstant.id:
            return

        if before.id in self._ignored[Event.member_update]:
            self._ignored[Event.member_update].remove(before.id)
            return

        diff = DeepDiff(before, after)
        changes = []
        done = []

        diff_values = {}

        diff_values.update(diff.get("values_changed", {}))
        diff_values.update(diff.get("type_changes", {}))
        diff_values.update(diff.get("iterable_item_removed", {}))
        diff_values.update(diff.get("iterable_item_added", {}))

        diff_user = DeepDiff(before._user, after._user)

        diff_values.update(diff_user.get("values_changed", {}))
        diff_values.update(diff_user.get("type_changes", {}))
        diff_values.update(diff_user.get("iterable_item_removed", {}))
        diff_values.update(diff_user.get("iterable_item_added", {}))

        for key, value in diff_values.items():
            if not key:  # Not sure why, but it happens
                continue

            key = key[5:]  # Remove "root." prefix

            if "[" in key:
                key = key.split("[", 1)[0]

            if "." in key:
                key = key.split(".", 1)[0]

            if key in done or key in MEMBER_CHANGES_SUPPRESSED:
                continue

            if key == "_roles":
                new_roles = after.roles
                old_roles = before.roles

                for role in old_roles:
                    if role not in new_roles:
                        changes.append(f"**Role removed:** {role.name} (`{role.id}`)")

                for role in new_roles:
                    if role not in old_roles:
                        changes.append(f"**Role added:** {role.name} (`{role.id}`)")

            else:
                new = value.get("new_value")
                old = value.get("old_value")

                if new and old:
                    changes.append(f"**{key.title()}:** `{old}` **->** `{new}`")

            done.append(key)

        if before.name != after.name:
            changes.append(
                f"**Username:** `{before.name}` **->** `{after.name}`"
            )

        if before.discriminator != after.discriminator:
            changes.append(
                f"**Discriminator:** `{before.discriminator}` **->** `{after.discriminator}`"
            )

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{Emojis.bullet} {item}\n"

        message = f"**{after.name}#{after.discriminator}** (`{after.id}`)\n{message}"

        await self.send_log_message(
            Icons.user_update, Colour.blurple(),
            "Member updated", message,
            thumbnail=after.avatar_url_as(static_format="png"),
            channel_id=Channels.userlog
        )

    async def on_raw_bulk_message_delete(self, event: RawBulkMessageDeleteEvent):
        if event.guild_id != GuildConstant.id or event.channel_id in GuildConstant.ignored:
            return

        # Could upload the log to the site - maybe we should store all the messages somewhere?
        # Currently if messages aren't in the cache, we ain't gonna have 'em.

        ignored_messages = 0

        for message_id in event.message_ids:
            if message_id in self._ignored[Event.message_delete]:
                self._ignored[Event.message_delete].remove(message_id)
                ignored_messages += 1

        if ignored_messages >= len(event.message_ids):
            return

        channel = self.bot.get_channel(event.channel_id)

        if channel.category:
            message = f"{len(event.message_ids)} deleted in {channel.category}/#{channel.name} (`{channel.id}`)"
        else:
            message = f"{len(event.message_ids)} deleted in #{channel.name} (`{channel.id}`)"

        await self.send_log_message(
            Icons.message_bulk_delete, Colour.orange(),
            "Bulk message delete",
            message, channel_id=Channels.devalerts,
            ping_everyone=True
        )

    async def on_message_delete(self, message: Message):
        channel = message.channel
        author = message.author

        if message.guild.id != GuildConstant.id or channel.id in GuildConstant.ignored:
            return

        self._cached_deletes.append(message.id)

        if message.id in self._ignored[Event.message_delete]:
            self._ignored[Event.message_delete].remove(message.id)
            return

        if author.bot:
            return

        if channel.category:
            response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
            )
        else:
            response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
            )

        # Shorten the message content if necessary
        content = message.clean_content
        remaining_chars = 2040 - len(response)

        if len(content) > remaining_chars:
            content = content[:remaining_chars] + "..."

        response += f"{content}"

        if message.attachments:
            # Prepend the message metadata with the number of attachments
            response = f"**Attachments:** {len(message.attachments)}\n" + response

        await self.send_log_message(
            Icons.message_delete, Colours.soft_red,
            "Message deleted",
            response,
            channel_id=Channels.message_log
        )

    async def on_raw_message_delete(self, event: RawMessageDeleteEvent):
        if event.guild_id != GuildConstant.id or event.channel_id in GuildConstant.ignored:
            return

        await asyncio.sleep(1)  # Wait here in case the normal event was fired

        if event.message_id in self._cached_deletes:
            # It was in the cache and the normal event was fired, so we can just ignore it
            self._cached_deletes.remove(event.message_id)
            return

        if event.message_id in self._ignored[Event.message_delete]:
            self._ignored[Event.message_delete].remove(event.message_id)
            return

        channel = self.bot.get_channel(event.channel_id)

        if channel.category:
            response = (
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{event.message_id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )
        else:
            response = (
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{event.message_id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )

        await self.send_log_message(
            Icons.message_delete, Colour(Colours.soft_red),
            "Message deleted",
            response,
            channel_id=Channels.message_log
        )

    async def on_message_edit(self, before: Message, after: Message):
        if (
            not before.guild
            or before.guild.id != GuildConstant.id
            or before.channel.id in GuildConstant.ignored
            or before.author.bot
        ):
            return

        self._cached_edits.append(before.id)

        if before.content == after.content:
            return

        author = before.author
        channel = before.channel

        if channel.category:
            before_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{before.id}`\n"
                "\n"
                f"{before.clean_content}"
            )

            after_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{before.id}`\n"
                "\n"
                f"{after.clean_content}"
            )
        else:
            before_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{before.id}`\n"
                "\n"
                f"{before.clean_content}"
            )

            after_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{before.id}`\n"
                "\n"
                f"{after.clean_content}"
            )

        if before.edited_at:
            # Message was previously edited, to assist with self-bot detection, use the edited_at
            # datetime as the baseline and create a human-readable delta between this edit event
            # and the last time the message was edited
            timestamp = before.edited_at
            delta = humanize_delta(relativedelta(after.edited_at, before.edited_at))
            footer = f"Last edited {delta} ago"
        else:
            # Message was not previously edited, use the created_at datetime as the baseline, no
            # delta calculation needed
            timestamp = before.created_at
            footer = None

        await self.send_log_message(
            Icons.message_edit, Colour.blurple(), "Message edited (Before)", before_response,
            channel_id=Channels.message_log, timestamp_override=timestamp, footer=footer
        )

        await self.send_log_message(
            Icons.message_edit, Colour.blurple(), "Message edited (After)", after_response,
            channel_id=Channels.message_log, timestamp_override=after.edited_at
        )

    async def on_raw_message_edit(self, event: RawMessageUpdateEvent):
        try:
            channel = self.bot.get_channel(int(event.data["channel_id"]))
            message = await channel.get_message(event.message_id)
        except NotFound:  # Was deleted before we got the event
            return

        if (
            not message.guild
            or message.guild.id != GuildConstant.id
            or message.channel.id in GuildConstant.ignored
            or message.author.bot
        ):
            return

        await asyncio.sleep(1)  # Wait here in case the normal event was fired

        if event.message_id in self._cached_edits:
            # It was in the cache and the normal event was fired, so we can just ignore it
            self._cached_edits.remove(event.message_id)
            return

        author = message.author
        channel = message.channel

        if channel.category:
            before_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )

            after_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                f"{message.clean_content}"
            )
        else:
            before_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )

            after_response = (
                f"**Author:** {author.name}#{author.discriminator} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
                f"{message.clean_content}"
            )

        await self.send_log_message(
            Icons.message_edit, Colour.blurple(), "Message edited (Before)",
            before_response, channel_id=Channels.message_log
        )

        await self.send_log_message(
            Icons.message_edit, Colour.blurple(), "Message edited (After)",
            after_response, channel_id=Channels.message_log
        )


def setup(bot):
    bot.add_cog(ModLog(bot))
    log.info("Cog loaded: ModLog")
