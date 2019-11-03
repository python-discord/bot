import asyncio
import difflib
import itertools
import logging
import typing as t
from datetime import datetime

import discord
from dateutil.relativedelta import relativedelta
from deepdiff import DeepDiff
from discord import Colour
from discord.abc import GuildChannel
from discord.ext.commands import Bot, Cog, Context

from bot.constants import Channels, Colours, Emojis, Event, Guild as GuildConstant, Icons, URLs
from bot.utils.time import humanize_delta
from .utils import UserTypes

log = logging.getLogger(__name__)

GUILD_CHANNEL = t.Union[discord.CategoryChannel, discord.TextChannel, discord.VoiceChannel]

CHANNEL_CHANGES_UNSUPPORTED = ("permissions",)
CHANNEL_CHANGES_SUPPRESSED = ("_overwrites", "position")
MEMBER_CHANGES_SUPPRESSED = ("status", "activities", "_client_status", "nick")
ROLE_CHANGES_UNSUPPORTED = ("colour", "permissions")


class ModLog(Cog, name="ModLog"):
    """Logging for server events and staff actions."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._ignored = {event: [] for event in Event}

        self._cached_deletes = []
        self._cached_edits = []

    async def upload_log(self, messages: t.List[discord.Message], actor_id: int) -> str:
        """
        Uploads the log data to the database via an API endpoint for uploading logs.

        Used in several mod log embeds.

        Returns a URL that can be used to view the log.
        """
        response = await self.bot.api_client.post(
            'bot/deleted-messages',
            json={
                'actor': actor_id,
                'creation': datetime.utcnow().isoformat(),
                'deletedmessage_set': [
                    {
                        'id': message.id,
                        'author': message.author.id,
                        'channel_id': message.channel.id,
                        'content': message.content,
                        'embeds': [embed.to_dict() for embed in message.embeds]
                    }
                    for message in messages
                ]
            }
        )

        return f"{URLs.site_logs_view}/{response['id']}"

    def ignore(self, event: Event, *items: int) -> None:
        """Add event to ignored events to suppress log emission."""
        for item in items:
            if item not in self._ignored[event]:
                self._ignored[event].append(item)

    async def send_log_message(
        self,
        icon_url: t.Optional[str],
        colour: t.Union[discord.Colour, int],
        title: t.Optional[str],
        text: str,
        thumbnail: t.Optional[t.Union[str, discord.Asset]] = None,
        channel_id: int = Channels.modlog,
        ping_everyone: bool = False,
        files: t.Optional[t.List[discord.File]] = None,
        content: t.Optional[str] = None,
        additional_embeds: t.Optional[t.List[discord.Embed]] = None,
        additional_embeds_msg: t.Optional[str] = None,
        timestamp_override: t.Optional[datetime] = None,
        footer: t.Optional[str] = None,
    ) -> Context:
        """Generate log embed and send to logging channel."""
        embed = discord.Embed(description=text)

        if title and icon_url:
            embed.set_author(name=title, icon_url=icon_url)

        embed.colour = colour
        embed.timestamp = timestamp_override or datetime.utcnow()

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
            if additional_embeds_msg:
                await channel.send(additional_embeds_msg)
            for additional_embed in additional_embeds:
                await channel.send(embed=additional_embed)

        return await self.bot.get_context(log_message)  # Optionally return for use with antispam

    @Cog.listener()
    async def on_guild_channel_create(self, channel: GUILD_CHANNEL) -> None:
        """Log channel create event to mod log."""
        if channel.guild.id != GuildConstant.id:
            return

        if isinstance(channel, discord.CategoryChannel):
            title = "Category created"
            message = f"{channel.name} (`{channel.id}`)"
        elif isinstance(channel, discord.VoiceChannel):
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

        await self.send_log_message(Icons.hash_green, Colours.soft_green, title, message)

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: GUILD_CHANNEL) -> None:
        """Log channel delete event to mod log."""
        if channel.guild.id != GuildConstant.id:
            return

        if isinstance(channel, discord.CategoryChannel):
            title = "Category deleted"
        elif isinstance(channel, discord.VoiceChannel):
            title = "Voice channel deleted"
        else:
            title = "Text channel deleted"

        if channel.category and not isinstance(channel, discord.CategoryChannel):
            message = f"{channel.category}/{channel.name} (`{channel.id}`)"
        else:
            message = f"{channel.name} (`{channel.id}`)"

        await self.send_log_message(
            Icons.hash_red, Colours.soft_red,
            title, message
        )

    @Cog.listener()
    async def on_guild_channel_update(self, before: GUILD_CHANNEL, after: GuildChannel) -> None:
        """Log channel update event to mod log."""
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

    @Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """Log role create event to mod log."""
        if role.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.crown_green, Colours.soft_green,
            "Role created", f"`{role.id}`"
        )

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Log role delete event to mod log."""
        if role.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.crown_red, Colours.soft_red,
            "Role removed", f"{role.name} (`{role.id}`)"
        )

    @Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Log role update event to mod log."""
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

    @Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """Log guild update event to mod log."""
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

    @Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, member: UserTypes) -> None:
        """Log ban event to user log."""
        if guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_ban]:
            self._ignored[Event.member_ban].remove(member.id)
            return

        await self.send_log_message(
            Icons.user_ban, Colours.soft_red,
            "User banned", f"{member} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png"),
            channel_id=Channels.userlog
        )

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Log member join event to user log."""
        if member.guild.id != GuildConstant.id:
            return

        message = f"{member} (`{member.id}`)"
        now = datetime.utcnow()
        difference = abs(relativedelta(now, member.created_at))

        message += "\n\n**Account age:** " + humanize_delta(difference)

        if difference.days < 1 and difference.months < 1 and difference.years < 1:  # New user account!
            message = f"{Emojis.new} {message}"

        await self.send_log_message(
            Icons.sign_in, Colours.soft_green,
            "User joined", message,
            thumbnail=member.avatar_url_as(static_format="png"),
            channel_id=Channels.userlog
        )

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Log member leave event to user log."""
        if member.guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_remove]:
            self._ignored[Event.member_remove].remove(member.id)
            return

        await self.send_log_message(
            Icons.sign_out, Colours.soft_red,
            "User left", f"{member} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png"),
            channel_id=Channels.userlog
        )

    @Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, member: discord.User) -> None:
        """Log member unban event to mod log."""
        if guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_unban]:
            self._ignored[Event.member_unban].remove(member.id)
            return

        await self.send_log_message(
            Icons.user_unban, Colour.blurple(),
            "User unbanned", f"{member} (`{member.id}`)",
            thumbnail=member.avatar_url_as(static_format="png"),
            channel_id=Channels.modlog
        )

    @Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Log member update event to user log."""
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

        if before.display_name != after.display_name:
            changes.append(
                f"**Display name:** `{before.display_name}` **->** `{after.display_name}`"
            )

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{Emojis.bullet} {item}\n"

        message = f"**{after}** (`{after.id}`)\n{message}"

        await self.send_log_message(
            Icons.user_update, Colour.blurple(),
            "Member updated", message,
            thumbnail=after.avatar_url_as(static_format="png"),
            channel_id=Channels.userlog
        )

    @Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Log message delete event to message change log."""
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
                f"**Author:** {author} (`{author.id}`)\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
            )
        else:
            response = (
                f"**Author:** {author} (`{author.id}`)\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                "\n"
            )

        if message.attachments:
            # Prepend the message metadata with the number of attachments
            response = f"**Attachments:** {len(message.attachments)}\n" + response

        # Shorten the message content if necessary
        content = message.clean_content
        remaining_chars = 2040 - len(response)

        if len(content) > remaining_chars:
            botlog_url = await self.upload_log(messages=[message], actor_id=message.author.id)
            ending = f"\n\nMessage truncated, [full message here]({botlog_url})."
            truncation_point = remaining_chars - len(ending)
            content = f"{content[:truncation_point]}...{ending}"

        response += f"{content}"

        await self.send_log_message(
            Icons.message_delete, Colours.soft_red,
            "Message deleted",
            response,
            channel_id=Channels.message_log
        )

    @Cog.listener()
    async def on_raw_message_delete(self, event: discord.RawMessageDeleteEvent) -> None:
        """Log raw message delete event to message change log."""
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
            Icons.message_delete, Colours.soft_red,
            "Message deleted",
            response,
            channel_id=Channels.message_log
        )

    @Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Log message edit event to message change log."""
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
        channel_name = f"{channel.category}/#{channel.name}" if channel.category else f"#{channel.name}"

        _before = before.clean_content
        _after = after.clean_content
        groups = tuple((g[0], tuple(g[1]))
                       for g in itertools.groupby(difflib.ndiff(_before.split(), _after.split()), key=lambda s: s[0]))

        for index, (name, values) in enumerate(groups):
            sub = ' '.join(s[2:].strip() for s in values)
            if name == '-':
                _before = _before.replace(sub, f"[{sub}](http://.z)")
            elif name == '+':
                _after = _after.replace(sub, f"[{sub}](http://.z)")
            else:
                if len(values) > 2:
                    new = (f"{values[0].strip() if index > 0 else ''}"
                           " ... "
                           f"{values[-1].strip() if index < len(groups) - 1 else ''}")
                else:
                    new = sub
                _before = _before.replace(sub, new)
                _after = _after.replace(sub, new)

        response = (
            f"**Author:** {author} (`{author.id}`)\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
            f"**Message ID:** `{before.id}`\n"
            "\n"
            f"**Before**:\n{_before}\n"
            f"**After**:\n{_after}\n"
            "\n"
            f"[jump to message]({after.jump_url})"
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
            Icons.message_edit, Colour.blurple(), "Message edited", response,
            channel_id=Channels.message_log, timestamp_override=timestamp, footer=footer
        )

    @Cog.listener()
    async def on_raw_message_edit(self, event: discord.RawMessageUpdateEvent) -> None:
        """Log raw message edit event to message change log."""
        try:
            channel = self.bot.get_channel(int(event.data["channel_id"]))
            message = await channel.fetch_message(event.message_id)
        except discord.NotFound:  # Was deleted before we got the event
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
        channel_name = f"{channel.category}/#{channel.name}" if channel.category else f"#{channel.name}"

        before_response = (
            f"**Author:** {author} (`{author.id}`)\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
            f"**Message ID:** `{message.id}`\n"
            "\n"
            "This message was not cached, so the message content cannot be displayed."
        )

        after_response = (
            f"**Author:** {author} (`{author.id}`)\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
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
