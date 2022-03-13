import asyncio
import difflib
import itertools
import typing as t
from datetime import datetime, timezone
from itertools import zip_longest

import disnake
from dateutil.relativedelta import relativedelta
from deepdiff import DeepDiff
from disnake import Colour, Message, Thread
from disnake.abc import GuildChannel
from disnake.ext.commands import Cog, Context
from disnake.utils import escape_markdown

from bot.bot import Bot
from bot.constants import Categories, Channels, Colours, Emojis, Event, Guild as GuildConstant, Icons, Roles, URLs
from bot.log import get_logger
from bot.utils import time
from bot.utils.messages import format_user

log = get_logger(__name__)

GUILD_CHANNEL = t.Union[disnake.CategoryChannel, disnake.TextChannel, disnake.VoiceChannel]

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

    async def upload_log(
        self,
        messages: t.Iterable[disnake.Message],
        actor_id: int,
        attachments: t.Iterable[t.List[str]] = None
    ) -> str:
        """Upload message logs to the database and return a URL to a page for viewing the logs."""
        if attachments is None:
            attachments = []

        response = await self.bot.api_client.post(
            'bot/deleted-messages',
            json={
                'actor': actor_id,
                'creation': datetime.now(timezone.utc).isoformat(),
                'deletedmessage_set': [
                    {
                        'id': message.id,
                        'author': message.author.id,
                        'channel_id': message.channel.id,
                        'content': message.content.replace("\0", ""),  # Null chars cause 400.
                        'embeds': [embed.to_dict() for embed in message.embeds],
                        'attachments': attachment,
                    }
                    for message, attachment in zip_longest(messages, attachments, fillvalue=[])
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
        colour: t.Union[disnake.Colour, int],
        title: t.Optional[str],
        text: str,
        thumbnail: t.Optional[t.Union[str, disnake.Asset]] = None,
        channel_id: int = Channels.mod_log,
        ping_everyone: bool = False,
        files: t.Optional[t.List[disnake.File]] = None,
        content: t.Optional[str] = None,
        additional_embeds: t.Optional[t.List[disnake.Embed]] = None,
        timestamp_override: t.Optional[datetime] = None,
        footer: t.Optional[str] = None,
    ) -> Context:
        """Generate log embed and send to logging channel."""
        await self.bot.wait_until_guild_available()
        # Truncate string directly here to avoid removing newlines
        embed = disnake.Embed(
            description=text[:4093] + "..." if len(text) > 4096 else text
        )

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
                content = f"<@&{Roles.moderators}> {content}"
            else:
                content = f"<@&{Roles.moderators}>"

        # Truncate content to 2000 characters and append an ellipsis.
        if content and len(content) > 2000:
            content = content[:2000 - 3] + "..."

        channel = self.bot.get_channel(channel_id)
        log_message = await channel.send(
            content=content,
            embed=embed,
            files=files
        )

        if additional_embeds:
            for additional_embed in additional_embeds:
                await channel.send(embed=additional_embed)

        return await self.bot.get_context(log_message)  # Optionally return for use with antispam

    @Cog.listener()
    async def on_guild_channel_create(self, channel: GUILD_CHANNEL) -> None:
        """Log channel create event to mod log."""
        if channel.guild.id != GuildConstant.id:
            return

        if isinstance(channel, disnake.CategoryChannel):
            title = "Category created"
            message = f"{channel.name} (`{channel.id}`)"
        elif isinstance(channel, disnake.VoiceChannel):
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

        if isinstance(channel, disnake.CategoryChannel):
            title = "Category deleted"
        elif isinstance(channel, disnake.VoiceChannel):
            title = "Voice channel deleted"
        else:
            title = "Text channel deleted"

        if channel.category and not isinstance(channel, disnake.CategoryChannel):
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

        # Two channel updates are sent for a single edit: 1 for topic and 1 for category change.
        # TODO: remove once support is added for ignoring multiple occurrences for the same channel.
        help_categories = (Categories.help_available, Categories.help_dormant, Categories.help_in_use)
        if after.category and after.category.id in help_categories:
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

        await self.send_log_message(
            Icons.hash_blurple, Colour.og_blurple(),
            "Channel updated", message
        )

    @Cog.listener()
    async def on_guild_role_create(self, role: disnake.Role) -> None:
        """Log role create event to mod log."""
        if role.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.crown_green, Colours.soft_green,
            "Role created", f"`{role.id}`"
        )

    @Cog.listener()
    async def on_guild_role_delete(self, role: disnake.Role) -> None:
        """Log role delete event to mod log."""
        if role.guild.id != GuildConstant.id:
            return

        await self.send_log_message(
            Icons.crown_red, Colours.soft_red,
            "Role removed", f"{role.name} (`{role.id}`)"
        )

    @Cog.listener()
    async def on_guild_role_update(self, before: disnake.Role, after: disnake.Role) -> None:
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

        await self.send_log_message(
            Icons.crown_blurple, Colour.og_blurple(),
            "Role updated", message
        )

    @Cog.listener()
    async def on_guild_update(self, before: disnake.Guild, after: disnake.Guild) -> None:
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

        await self.send_log_message(
            Icons.guild_update, Colour.og_blurple(),
            "Guild updated", message,
            thumbnail=after.icon.with_static_format("png")
        )

    @Cog.listener()
    async def on_member_ban(self, guild: disnake.Guild, member: disnake.Member) -> None:
        """Log ban event to user log."""
        if guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_ban]:
            self._ignored[Event.member_ban].remove(member.id)
            return

        await self.send_log_message(
            Icons.user_ban, Colours.soft_red,
            "User banned", format_user(member),
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log
        )

    @Cog.listener()
    async def on_member_join(self, member: disnake.Member) -> None:
        """Log member join event to user log."""
        if member.guild.id != GuildConstant.id:
            return

        now = datetime.now(timezone.utc)
        difference = abs(relativedelta(now, member.created_at))

        message = format_user(member) + "\n\n**Account age:** " + time.humanize_delta(difference)

        if difference.days < 1 and difference.months < 1 and difference.years < 1:  # New user account!
            message = f"{Emojis.new} {message}"

        await self.send_log_message(
            Icons.sign_in, Colours.soft_green,
            "User joined", message,
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log
        )

    @Cog.listener()
    async def on_member_remove(self, member: disnake.Member) -> None:
        """Log member leave event to user log."""
        if member.guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_remove]:
            self._ignored[Event.member_remove].remove(member.id)
            return

        await self.send_log_message(
            Icons.sign_out, Colours.soft_red,
            "User left", format_user(member),
            thumbnail=member.display_avatar.url,
            channel_id=Channels.user_log
        )

    @Cog.listener()
    async def on_member_unban(self, guild: disnake.Guild, member: disnake.User) -> None:
        """Log member unban event to mod log."""
        if guild.id != GuildConstant.id:
            return

        if member.id in self._ignored[Event.member_unban]:
            self._ignored[Event.member_unban].remove(member.id)
            return

        await self.send_log_message(
            Icons.user_unban, Colour.og_blurple(),
            "User unbanned", format_user(member),
            thumbnail=member.display_avatar.url,
            channel_id=Channels.mod_log
        )

    @staticmethod
    def get_role_diff(before: t.List[disnake.Role], after: t.List[disnake.Role]) -> t.List[str]:
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
    async def on_member_update(self, before: disnake.Member, after: disnake.Member) -> None:
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

        await self.send_log_message(
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

    def is_channel_ignored(self, channel_id: int) -> bool:
        """
        Return true if the channel, or parent channel in the case of threads, passed should be ignored by modlog.

        Currently ignored channels are:
        1. Channels not in the guild we care about (constants.Guild.id).
        2. Channels that mods do not have view permissions to
        3. Channels in constants.Guild.modlog_blacklist
        """
        channel = self.bot.get_channel(channel_id)

        # Ignore not found channels, DMs, and messages outside of the main guild.
        if not channel or not hasattr(channel, "guild") or channel.guild.id != GuildConstant.id:
            return True

        # Look at the parent channel of a thread.
        if isinstance(channel, Thread):
            channel = channel.parent

        # Mod team doesn't have view permission to the channel.
        if not channel.permissions_for(channel.guild.get_role(Roles.mod_team)).view_channel:
            return True

        return channel.id in GuildConstant.modlog_blacklist

    async def log_cached_deleted_message(self, message: disnake.Message) -> None:
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
                f"[Jump to message]({message.jump_url})\n"
                "\n"
            )
        else:
            response = (
                f"**Author:** {format_user(author)}\n"
                f"**Channel:** #{channel.name} (`{channel.id}`)\n"
                f"**Message ID:** `{message.id}`\n"
                f"[Jump to message]({message.jump_url})\n"
                "\n"
            )

        if message.attachments:
            # Prepend the message metadata with the number of attachments
            response = f"**Attachments:** {len(message.attachments)}\n" + response

        # Shorten the message content if necessary
        content = message.clean_content
        remaining_chars = 4090 - len(response)

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

    async def log_uncached_deleted_message(self, event: disnake.RawMessageDeleteEvent) -> None:
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
    async def on_raw_message_delete(self, event: disnake.RawMessageDeleteEvent) -> None:
        """Log message deletions to message change log."""
        if event.cached_message is not None:
            await self.log_cached_deleted_message(event.cached_message)
        else:
            await self.log_uncached_deleted_message(event)

    @Cog.listener()
    async def on_message_edit(self, msg_before: disnake.Message, msg_after: disnake.Message) -> None:
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

        content_before: t.List[str] = []
        content_after: t.List[str] = []

        for index, (diff_type, words) in enumerate(diff_groups):
            sub = ' '.join(words)
            if diff_type == '-':
                content_before.append(f"[{sub}](http://o.hi)")
            elif diff_type == '+':
                content_after.append(f"[{sub}](http://o.hi)")
            elif diff_type == ' ':
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

        await self.send_log_message(
            Icons.message_edit, Colour.og_blurple(), "Message edited", response,
            channel_id=Channels.message_log, timestamp_override=timestamp, footer=footer
        )

    @Cog.listener()
    async def on_raw_message_edit(self, event: disnake.RawMessageUpdateEvent) -> None:
        """Log raw message edit event to message change log."""
        if event.guild_id is None:
            return  # ignore DM edits

        await self.bot.wait_until_guild_available()
        try:
            channel = self.bot.get_channel(int(event.data["channel_id"]))
            message = await channel.fetch_message(event.message_id)
        except disnake.NotFound:  # Was deleted before we got the event
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

        await self.send_log_message(
            Icons.message_edit, Colour.og_blurple(), "Message edited (Before)",
            before_response, channel_id=Channels.message_log
        )

        await self.send_log_message(
            Icons.message_edit, Colour.og_blurple(), "Message edited (After)",
            after_response, channel_id=Channels.message_log
        )

    @Cog.listener()
    async def on_thread_update(self, before: Thread, after: Thread) -> None:
        """Log thread archiving, un-archiving and name edits."""
        if self.is_channel_ignored(after.id):
            log.trace("Ignoring update of thread %s (%d)", after.mention, after.id)
            return

        if before.name != after.name:
            await self.send_log_message(
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

        await self.send_log_message(
            icon,
            colour,
            f"Thread {action}",
            (
                f"Thread {after.mention} ({after.name}, `{after.id}`) from {after.parent.mention} "
                f"(`{after.parent.id}`) was {action}"
            )
        )

    @Cog.listener()
    async def on_thread_delete(self, thread: Thread) -> None:
        """Log thread deletion."""
        if self.is_channel_ignored(thread.id):
            log.trace("Ignoring deletion of thread %s (%d)", thread.mention, thread.id)
            return

        await self.send_log_message(
            Icons.hash_red,
            Colours.soft_red,
            "Thread deleted",
            (
                f"Thread {thread.mention} ({thread.name}, `{thread.id}`) from {thread.parent.mention} "
                f"(`{thread.parent.id}`) deleted"
            )
        )

    @Cog.listener()
    async def on_thread_join(self, thread: Thread) -> None:
        """Log thread creation."""
        # If we are in the thread already we can most probably assume we already logged it?
        # We don't really have a better way of doing this since the API doesn't make any difference between the two
        if thread.me:
            return

        if self.is_channel_ignored(thread.id):
            log.trace("Ignoring creation of thread %s (%d)", thread.mention, thread.id)
            return

        await self.send_log_message(
            Icons.hash_green,
            Colours.soft_green,
            "Thread created",
            (
                f"Thread {thread.mention} ({thread.name}, `{thread.id}`) from {thread.parent.mention} "
                f"(`{thread.parent.id}`) created"
            )
        )

    @Cog.listener()
    async def on_voice_state_update(
        self,
        member: disnake.Member,
        before: disnake.VoiceState,
        after: disnake.VoiceState
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

        await self.send_log_message(
            icon_url=icon,
            colour=colour,
            title="Voice state updated",
            text=message,
            thumbnail=member.display_avatar.url,
            channel_id=Channels.voice_log
        )


def setup(bot: Bot) -> None:
    """Load the ModLog cog."""
    bot.add_cog(ModLog(bot))
