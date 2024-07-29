import asyncio
import difflib
import itertools
from datetime import UTC, datetime

import discord
from dateutil.relativedelta import relativedelta
from deepdiff import DeepDiff
from discord import Colour, Message, Thread
from discord.abc import GuildChannel
from discord.ext.commands import Cog
from discord.utils import escape_markdown, format_dt, snowflake_time
from pydis_core.utils.channel import get_or_fetch_channel

from bot.bot import Bot
from bot.constants import Channels, Colours, Emojis, Event, Guild as GuildConstant, Icons, Roles
from bot.log import get_logger
from bot.utils import time
from bot.utils.messages import format_user, upload_log
from bot.utils.modlog import send_log_message

log = get_logger(__name__)

GUILD_CHANNEL = discord.CategoryChannel | discord.TextChannel | discord.VoiceChannel

CHANNEL_CHANGES_UNSUPPORTED = ("permissions",)
CHANNEL_CHANGES_SUPPRESSED = ("_overwrites", "position")
ROLE_CHANGES_UNSUPPORTED = ("colour", "permissions")

VOICE_STATE_ATTRIBUTES = {
    "channel.name": "Channel",
    "self_stream": "Streaming",
    "self_video": "Broadcasting",
}


class ModLog(Cog, name="ModLog"):
    """Logging for server events and staff actions."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self._ignored = {event: [] for event in Event}

        self._cached_edits = []

    def ignore(self, event: Event, *items: int) -> None:
        """Add event to ignored events to suppress log emission."""
        for item in items:
            if item not in self._ignored[event]:
                self._ignored[event].append(item)

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

        await send_log_message(self.bot, Icons.hash_green, Colours.soft_green, title, message)

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

        await send_log_message(
            self.bot,
            Icons.hash_red,
            Colours.soft_red,
            title,
            message
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

                # Discord does not treat consecutive backticks ("``") as an empty inline code block, so the markdown
                # formatting is broken when `new` and/or `old` are empty values. "None" is used for these cases so
                # formatting is preserved.
                changes.append(f"**{key.title()}:** `{old or 'None'}` **→** `{new or 'None'}`")

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

        await send_log_message(
            self.bot,
            Icons.hash_blurple,
            Colour.og_blurple(),
            "Channel updated",
            message
        )

    @Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """Log role create event to mod log."""
        if role.guild.id != GuildConstant.id:
            return

        await send_log_message(
            self.bot,
            Icons.crown_green,
            Colours.soft_green,
            "Role created",
            f"`{role.id}`"
        )

    @Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Log role delete event to mod log."""
        if role.guild.id != GuildConstant.id:
            return

        await send_log_message(
            self.bot,
            Icons.crown_red,
            Colours.soft_red,
            "Role removed",
            f"{role.name} (`{role.id}`)"
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

                changes.append(f"**{key.title()}:** `{old}` **→** `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{Emojis.bullet} {item}\n"

        message = f"**{after.name}** (`{after.id}`)\n{message}"

        await send_log_message(
            self.bot,
            Icons.crown_blurple,
            Colour.og_blurple(),
            "Role updated",
            message
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

            changes.append(f"**{key.title()}:** `{old}` **→** `{new}`")

            done.append(key)

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{Emojis.bullet} {item}\n"

        message = f"**{after.name}** (`{after.id}`)\n{message}"

        await send_log_message(
            self.bot,
            Icons.guild_update,
            Colour.og_blurple(),
            "Guild updated",
            message,
            thumbnail=after.icon.with_static_format("png")
        )

    @Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, member: discord.Member) -> None:
        """Log ban event to user log."""
        if guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_ban]:
            self._ignored[Event.member_ban].remove(member.id)
            return

        await send_log_message(
            self.bot,
            Icons.user_ban,
            Colours.soft_red,
            "User banned",
            format_user(member),
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log
        )

    @Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Log member join event to user log."""
        if member.guild.id != GuildConstant.id:
            return

        now = datetime.now(tz=UTC)
        difference = abs(relativedelta(now, member.created_at))

        message = format_user(member) + "\n\n**Account age:** " + time.humanize_delta(difference)

        if difference.days < 1 and difference.months < 1 and difference.years < 1:  # New user account!
            message = f"{Emojis.new} {message}"

        await send_log_message(
            self.bot,
            Icons.sign_in,
            Colours.soft_green,
            "User joined",
            message,
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log
        )

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Log member leave event to user log."""
        if member.guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_remove]:
            self._ignored[Event.member_remove].remove(member.id)
            return

        await send_log_message(
            self.bot,
            Icons.sign_out,
            Colours.soft_red,
            "User left",
            format_user(member),
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log
        )

    @Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, member: discord.User) -> None:
        """Log member unban event to mod log."""
        if guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_unban]:
            self._ignored[Event.member_unban].remove(member.id)
            return

        await send_log_message(
            self.bot,
            Icons.user_unban,
            Colour.og_blurple(),
            "User unbanned",
            format_user(member),
            thumbnail=member.display_avatar.url,
            channel_id=Channels.mod_log
        )

    @staticmethod
    def get_role_diff(before: list[discord.Role], after: list[discord.Role]) -> list[str]:
        """Return a list of strings describing the roles added and removed."""
        changes = []
        before_roles = set(before)
        after_roles = set(after)

        for role in (before_roles - after_roles):
            changes.append(f"**Role removed:** {role.name} (`{role.id}`)")

        for role in (after_roles - before_roles):
            changes.append(f"**Role added:** {role.name} (`{role.id}`)")

        return changes

    @Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Log member update event to user log."""
        if before.guild.id != GuildConstant.id:
            return

        if before.id in self._ignored[Event.member_update]:
            self._ignored[Event.member_update].remove(before.id)
            return

        changes = self.get_role_diff(before.roles, after.roles)

        # The regex is a simple way to exclude all sequence and mapping types.
        diff = DeepDiff(before, after, exclude_regex_paths=r".*\[.*")

        # A type change seems to always take precedent over a value change. Furthermore, it will
        # include the value change along with the type change anyway. Therefore, it's OK to
        # "overwrite" values_changed; in practice there will never even be anything to overwrite.
        diff_values = {**diff.get("values_changed", {}), **diff.get("type_changes", {})}

        for attr, value in diff_values.items():
            if not attr:  # Not sure why, but it happens.
                continue

            attr = attr[5:]  # Remove "root." prefix.
            attr = attr.replace("_", " ").replace(".", " ").capitalize()

            new = value.get("new_value")
            old = value.get("old_value")

            changes.append(f"**{attr}:** `{old}` **→** `{new}`")

        if not changes:
            return

        message = ""

        for item in sorted(changes):
            message += f"{Emojis.bullet} {item}\n"

        message = f"{format_user(after)}\n{message}"

        await send_log_message(
            self.bot,
            icon_url=Icons.user_update,
            colour=Colour.og_blurple(),
            title="Member updated",
            text=message,
            thumbnail=after.display_avatar.url,
            channel_id=Channels.user_log
        )

    def is_message_blacklisted(self, message: Message) -> bool:
        """Return true if the message is in a blacklisted thread or channel."""
        # Ignore bots or DMs
        if message.author.bot or not message.guild:
            return True

        return self.is_channel_ignored(message.channel.id)

    def is_channel_ignored(self, channel: int | GuildChannel | Thread) -> bool:
        """
        Return true if the channel, or parent channel in the case of threads, passed should be ignored by modlog.

        Currently ignored channels are:
        1. Channels not in the guild we care about (constants.Guild.id).
        2. Channels that mods do not have view permissions to
        3. Channels in constants.Guild.modlog_blacklist
        """
        if isinstance(channel, int):
            channel = self.bot.get_channel(channel)

        # Ignore not found channels, DMs, and messages outside of the main guild.
        if not channel or channel.guild is None or channel.guild.id != GuildConstant.id:
            return True

        # Look at the parent channel of a thread.
        if isinstance(channel, Thread):
            channel = channel.parent

        # Mod team doesn't have view permission to the channel.
        if not channel.permissions_for(channel.guild.get_role(Roles.mod_team)).view_channel:
            return True

        return channel.id in GuildConstant.modlog_blacklist

    async def log_cached_deleted_message(self, message: discord.Message) -> None:
        """
        Log the message's details to message change log.

        This is called when a cached message is deleted.
        """
        channel = message.channel
        author = message.author

        if self.is_message_blacklisted(message):
            return

        if message.id in self._ignored[Event.message_delete]:
            self._ignored[Event.message_delete].remove(message.id)
            return

        if channel.category:
            response = (
                f"**Author:** {format_user(author)}\n"
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                f"**Sent at:** {format_dt(message.created_at)}\n"
                f"[Jump to message]({message.jump_url})\n"
            )
        else:
            response = (
                f"**Author:** {format_user(author)}\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                f"**Sent at:** {format_dt(message.created_at)}\n"
                f"[Jump to message]({message.jump_url})\n"
            )

        # If the message is a reply, add the reference to the response
        if message.reference is not None and message.reference.resolved is not None:
            resolved_message = message.reference.resolved

            if isinstance(resolved_message, discord.DeletedReferencedMessage):
                # Reference is a deleted message
                reference_line = f"**In reply to:** `{resolved_message.id}`(Deleted Message)\n"
                response = reference_line + response

            elif isinstance(resolved_message, discord.Message):
                jump_url = resolved_message.jump_url
                author = resolved_message.author.mention

                reference_line = (
                    f"**In reply to:** {author} [Jump to referenced message]({jump_url})\n"
                )
                response = reference_line + response

        elif message.reference is not None and message.reference.resolved is None:
            reference_line = (
                "**In reply to:** (Message could not be resolved)\n"
            )
            response = reference_line + response

        if message.attachments:
            # Prepend the message metadata with the number of attachments
            response = f"**Attachments:** {len(message.attachments)}\n" + response

        # Shorten the message content if necessary
        response += "\n**Deleted Message:**:\n"
        content = message.clean_content
        remaining_chars = 4090 - len(response)

        if len(content) > remaining_chars:
            botlog_url = await upload_log(messages=[message], actor_id=message.author.id)
            ending = f"\n\nMessage truncated, [full message here]({botlog_url})."
            truncation_point = remaining_chars - len(ending)
            content = f"{content[:truncation_point]}...{ending}"

        response += f"{content}"

        await send_log_message(
            self.bot,
            Icons.message_delete,
            Colours.soft_red,
            "Message deleted",
            response,
            channel_id=Channels.message_log
        )

    async def log_uncached_deleted_message(self, event: discord.RawMessageDeleteEvent) -> None:
        """
        Log the message's details to message change log.

        This is called when a message absent from the cache is deleted.
        Hence, the message contents aren't logged.
        """
        await self.bot.wait_until_guild_available()
        if self.is_channel_ignored(event.channel_id):
            return

        if event.message_id in self._ignored[Event.message_delete]:
            self._ignored[Event.message_delete].remove(event.message_id)
            return

        channel = self.bot.get_channel(event.channel_id)

        if channel.category:
            response = (
                f"**Channel:** {channel.category}/#{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{event.message_id}`\n"
                f"**Sent at:** {format_dt(snowflake_time(event.message_id))}\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )
        else:
            response = (
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{event.message_id}`\n"
                f"**Sent at:** {format_dt(snowflake_time(event.message_id))}\n"
                "\n"
                "This message was not cached, so the message content cannot be displayed."
            )

        await send_log_message(
            self.bot,
            Icons.message_delete,
            Colours.soft_red,
            "Message deleted",
            response,
            channel_id=Channels.message_log
        )

    @Cog.listener()
    async def on_raw_message_delete(self, event: discord.RawMessageDeleteEvent) -> None:
        """Log message deletions to message change log."""
        if event.cached_message is not None:
            await self.log_cached_deleted_message(event.cached_message)
        else:
            await self.log_uncached_deleted_message(event)

    @Cog.listener()
    async def on_message_edit(self, msg_before: discord.Message, msg_after: discord.Message) -> None:
        """Log message edit event to message change log."""
        if self.is_message_blacklisted(msg_before):
            return

        self._cached_edits.append(msg_before.id)

        if msg_before.content == msg_after.content:
            return

        channel = msg_before.channel
        channel_name = f"{channel.category}/#{channel.name}" if channel.category else f"#{channel.name}"

        cleaned_contents = (escape_markdown(msg.clean_content).split() for msg in (msg_before, msg_after))
        # Getting the difference per words and group them by type - add, remove, same
        # Note that this is intended grouping without sorting
        diff = difflib.ndiff(*cleaned_contents)
        diff_groups = tuple(
            (diff_type, tuple(s[2:] for s in diff_words))
            for diff_type, diff_words in itertools.groupby(diff, key=lambda s: s[0])
        )

        content_before: list[str] = []
        content_after: list[str] = []

        for index, (diff_type, words) in enumerate(diff_groups):
            sub = " ".join(words)
            if diff_type == "-":
                content_before.append(f"[{sub}](http://o.hi)")
            elif diff_type == "+":
                content_after.append(f"[{sub}](http://o.hi)")
            elif diff_type == " ":
                if len(words) > 2:
                    sub = (
                        f"{words[0] if index > 0 else ''}"
                        " ... "
                        f"{words[-1] if index < len(diff_groups) - 1 else ''}"
                    )
                content_before.append(sub)
                content_after.append(sub)

        response = (
            f"**Author:** {format_user(msg_before.author)}\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
            f"**Message ID:** `{msg_before.id}`\n"
            "\n"
            f"**Before**:\n{' '.join(content_before)}\n"
            f"**After**:\n{' '.join(content_after)}\n"
            "\n"
            f"[Jump to message]({msg_after.jump_url})"
        )

        if msg_before.edited_at:
            # Message was previously edited, to assist with self-bot detection, use the edited_at
            # datetime as the baseline and create a human-readable delta between this edit event
            # and the last time the message was edited
            timestamp = msg_before.edited_at
            delta = time.humanize_delta(msg_after.edited_at, msg_before.edited_at)
            footer = f"Last edited {delta} ago"
        else:
            # Message was not previously edited, use the created_at datetime as the baseline, no
            # delta calculation needed
            timestamp = msg_before.created_at
            footer = None

        await send_log_message(
            self.bot,
            Icons.message_edit,
            Colour.og_blurple(),
            "Message edited",
            response,
            channel_id=Channels.message_log,
            timestamp_override=timestamp,
            footer=footer
        )

    @Cog.listener()
    async def on_raw_message_edit(self, event: discord.RawMessageUpdateEvent) -> None:
        """Log raw message edit event to message change log."""
        if event.guild_id is None:
            return  # ignore DM edits

        await self.bot.wait_until_guild_available()
        try:
            channel = await get_or_fetch_channel(self.bot, int(event.data["channel_id"]))
            message = await channel.fetch_message(event.message_id)
        except discord.NotFound:  # Channel/message was deleted before we got the event
            return

        if self.is_message_blacklisted(message):
            return

        await asyncio.sleep(1)  # Wait here in case the normal event was fired

        if event.message_id in self._cached_edits:
            # It was in the cache and the normal event was fired, so we can just ignore it
            self._cached_edits.remove(event.message_id)
            return

        channel = message.channel
        channel_name = f"{channel.category}/#{channel.name}" if channel.category else f"#{channel.name}"

        before_response = (
            f"**Author:** {format_user(message.author)}\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
            f"**Message ID:** `{message.id}`\n"
            "\n"
            "This message was not cached, so the message content cannot be displayed."
        )

        after_response = (
            f"**Author:** {format_user(message.author)}\n"
            f"**Channel:** {channel_name} (`{channel.id}`)\n"
            f"**Message ID:** `{message.id}`\n"
            "\n"
            f"{message.clean_content}"
        )

        await send_log_message(
            self.bot,
            Icons.message_edit,
            Colour.og_blurple(),
            "Message edited (Before)",
            before_response,
            channel_id=Channels.message_log
        )

        await send_log_message(
            self.bot,
            Icons.message_edit,
            Colour.og_blurple(),
            "Message edited (After)",
            after_response,
            channel_id=Channels.message_log
        )

    @Cog.listener()
    async def on_thread_update(self, before: Thread, after: Thread) -> None:
        """Log thread archiving, un-archiving and name edits."""
        if self.is_channel_ignored(after.id):
            log.trace("Ignoring update of thread %s (%d)", after.mention, after.id)
            return

        if before.name != after.name:
            await send_log_message(
                self.bot,
                Icons.hash_blurple,
                Colour.og_blurple(),
                "Thread name edited",
                (
                    f"Thread {after.mention} (`{after.id}`) from {after.parent.mention} (`{after.parent.id}`): "
                    f"`{before.name}` -> `{after.name}`"
                )
            )
            return

        if not before.archived and after.archived:
            colour = Colours.soft_red
            action = "archived"
            icon = Icons.hash_red
        elif before.archived and not after.archived:
            colour = Colours.soft_green
            action = "un-archived"
            icon = Icons.hash_green
        else:
            return

        await send_log_message(
            self.bot,
            icon,
            colour,
            f"Thread {action}",
            (
                f"Thread {after.mention} ({after.name}, `{after.id}`) from {after.parent.mention} "
                f"(`{after.parent.id}`) was {action}"
            ),
            channel_id=Channels.message_log,
        )

    @Cog.listener()
    async def on_thread_delete(self, thread: Thread) -> None:
        """Log thread deletion."""
        if self.is_channel_ignored(thread):
            log.trace("Ignoring deletion of thread %s (%d)", thread.mention, thread.id)
            return

        await send_log_message(
            self.bot,
            Icons.hash_red,
            Colours.soft_red,
            "Thread deleted",
            (
                f"Thread {thread.mention} ({thread.name}, `{thread.id}`) from {thread.parent.mention} "
                f"(`{thread.parent.id}`) deleted"
            ),
            channel_id=Channels.message_log,
        )

    @Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Log member voice state changes to the voice log channel."""
        if (
            member.guild.id != GuildConstant.id
            or (before.channel and self.is_channel_ignored(before.channel.id))
            or (after.channel and self.is_channel_ignored(after.channel.id))
        ):
            return

        if member.id in self._ignored[Event.voice_state_update]:
            self._ignored[Event.voice_state_update].remove(member.id)
            return

        # Exclude all channel attributes except the name.
        diff = DeepDiff(
            before,
            after,
            exclude_paths=("root.session_id", "root.afk"),
            exclude_regex_paths=r"root\.channel\.(?!name)",
        )

        # A type change seems to always take precedent over a value change. Furthermore, it will
        # include the value change along with the type change anyway. Therefore, it's OK to
        # "overwrite" values_changed; in practice there will never even be anything to overwrite.
        diff_values = {**diff.get("values_changed", {}), **diff.get("type_changes", {})}

        icon = Icons.voice_state_blue
        colour = Colour.og_blurple()
        changes = []

        for attr, values in diff_values.items():
            if not attr:  # Not sure why, but it happens.
                continue

            old = values["old_value"]
            new = values["new_value"]

            attr = attr[5:]  # Remove "root." prefix.
            attr = VOICE_STATE_ATTRIBUTES.get(attr, attr.replace("_", " ").capitalize())

            changes.append(f"**{attr}:** `{old}` **→** `{new}`")

            # Set the embed icon and colour depending on which attribute changed.
            if any(name in attr for name in ("Channel", "deaf", "mute")):
                if new is None or new is True:
                    # Left a channel or was muted/deafened.
                    icon = Icons.voice_state_red
                    colour = Colours.soft_red
                elif old is None or old is True:
                    # Joined a channel or was unmuted/undeafened.
                    icon = Icons.voice_state_green
                    colour = Colours.soft_green

        if not changes:
            return

        message = "\n".join(f"{Emojis.bullet} {item}" for item in sorted(changes))
        message = f"{format_user(member)}\n{message}"

        await send_log_message(
            self.bot,
            icon_url=icon,
            colour=colour,
            title="Voice state updated",
            text=message,
            thumbnail=member.display_avatar.url,
            channel_id=Channels.voice_log
        )


async def setup(bot: Bot) -> None:
    """Load the ModLog cog."""
    await bot.add_cog(ModLog(bot))
