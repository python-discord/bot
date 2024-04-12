from __future__ import annotations

import enum
import re
import time
from pathlib import Path
from typing import Literal, NamedTuple

import discord
import frontmatter
from discord import Embed, Interaction, Member, app_commands
from discord.ext.commands import Cog, Context

from bot import constants
from bot.bot import Bot
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils.messages import wait_for_deletion

log = get_logger(__name__)

TEST_CHANNELS = (
    constants.Channels.bot_commands,
    constants.Channels.helpers
)

REGEX_NON_ALPHABET = re.compile(r"[^a-z]", re.MULTILINE & re.IGNORECASE)
FOOTER_TEXT = "To show a tag, use /tag <tagname>."


class COOLDOWN(enum.Enum):
    """Sentinel value to signal that a tag is on cooldown."""

    obj = object()


class TagIdentifier(NamedTuple):
    """Stores the group and name used as an identifier for a tag."""

    group: str | None
    name: str

    def get_fuzzy_score(self, fuzz_tag_identifier: TagIdentifier) -> float:
        """Get fuzzy score, using `fuzz_tag_identifier` as the identifier to fuzzy match with."""
        if (self.group is None) != (fuzz_tag_identifier.group is None):
            # Ignore tags without groups if the identifier has a group and vice versa
            return .0
        if self.group == fuzz_tag_identifier.group:
            # Completely identical, or both None
            group_score = 1
        else:
            group_score = _fuzzy_search(fuzz_tag_identifier.group, self.group)

        fuzzy_score = group_score * _fuzzy_search(fuzz_tag_identifier.name, self.name) * 100
        if fuzzy_score:
            log.trace(f"Fuzzy score {fuzzy_score:=06.2f} for tag {self!r} with fuzz {fuzz_tag_identifier!r}")
        return fuzzy_score

    def __str__(self) -> str:
        if self.group is not None:
            return f"{self.group} {self.name}"
        return self.name

    @classmethod
    def from_string(cls, string: str) -> TagIdentifier:
        """Create a `TagIdentifier` instance from the beginning of `string`."""
        split_string = string.removeprefix(constants.Bot.prefix).split(" ", maxsplit=2)
        if len(split_string) == 1:
            return cls(None, split_string[0])
        return cls(split_string[0], split_string[1])


class Tag:
    """Provide an interface to a tag from resources with `file_content`."""

    def __init__(self, content_path: Path):
        post = frontmatter.loads(content_path.read_text("utf8"))
        self.file_path = content_path
        self.content = post.content
        self.metadata = post.metadata
        self._restricted_to: set[int] = set(self.metadata.get("restricted_to", ()))
        self._cooldowns: dict[discord.TextChannel, float] = {}
        self.aliases: list[str] = self.metadata.get("aliases", [])

    @property
    def embed(self) -> Embed:
        """Create an embed for the tag."""
        embed = Embed.from_dict(self.metadata.get("embed", {}))
        embed.description = self.content
        return embed

    def accessible_by(self, member: Member) -> bool:
        """Check whether `member` can access the tag."""
        return bool(
            not self._restricted_to
            or self._restricted_to & {role.id for role in member.roles}
        )

    def on_cooldown_in(self, channel: discord.TextChannel) -> bool:
        """Check whether the tag is on cooldown in `channel`."""
        return self._cooldowns.get(channel, float("-inf")) > time.time()

    def set_cooldown_for(self, channel: discord.TextChannel) -> None:
        """Set the tag to be on cooldown in `channel` for `constants.Cooldowns.tags` seconds."""
        self._cooldowns[channel] = time.time() + constants.Cooldowns.tags


def _fuzzy_search(search: str, target: str) -> float:
    """A simple scoring algorithm based on how many letters are found / total, with order in mind."""
    _search = REGEX_NON_ALPHABET.sub("", search.lower())
    if not _search:
        return 0

    _targets = iter(REGEX_NON_ALPHABET.split(target.lower()))

    current = 0
    for _target in _targets:
        index = 0
        try:
            while index < len(_target) and _search[current] == _target[index]:
                current += 1
                index += 1
        except IndexError:
            # Exit when _search runs out
            break

    return current / len(_search)


class Tags(Cog):
    """Fetch tags by name or content."""

    PAGINATOR_DEFAULTS = dict(max_lines=15, empty=False, footer_text=FOOTER_TEXT)

    def __init__(self, bot: Bot):
        self.bot = bot
        self.tags: dict[TagIdentifier, Tag] = {}
        self.initialize_tags()

    def initialize_tags(self) -> None:
        """Load all tags from resources into `self.tags`."""
        base_path = Path("bot", "resources", "tags")

        for file in base_path.glob("**/*"):
            if file.is_file():
                parent_dir = file.relative_to(base_path).parent
                tag_name = file.stem
                # Files directly under `base_path` have an empty string as the parent directory name
                tag_group = parent_dir.name or None

                tag = Tag(file)
                self.tags[TagIdentifier(tag_group, tag_name)] = tag

                for alias in tag.aliases:
                    self.tags[TagIdentifier(tag_group, alias)] = tag

    def _get_suggestions(self, tag_identifier: TagIdentifier) -> list[tuple[TagIdentifier, Tag]]:
        """Return a list of suggested tags for `tag_identifier`."""
        for threshold in [100, 90, 80, 70, 60]:
            suggestions = [
                (identifier, tag)
                for identifier, tag in self.tags.items()
                if identifier.get_fuzzy_score(tag_identifier) >= threshold
            ]
            if suggestions:
                return suggestions

        return []

    def get_fuzzy_matches(self, tag_identifier: TagIdentifier) -> list[tuple[TagIdentifier, Tag]]:
        """Get tags with identifiers similar to `tag_identifier`."""
        suggestions = []

        if tag_identifier.group is not None and len(tag_identifier.group) >= 2:
            # Try fuzzy matching with only a name first
            suggestions += self._get_suggestions(TagIdentifier(None, tag_identifier.group))

        if len(tag_identifier.name) >= 2:
            suggestions += self._get_suggestions(tag_identifier)

        return suggestions

    async def get_tag_embed(
            self,
            member: Member,
            channel: discord.abc.Messageable,
            tag_identifier: TagIdentifier,
    ) -> Embed | Literal[COOLDOWN.obj] | None:
        """
        Generate an embed of the requested tag or of suggestions if the tag doesn't exist
        or isn't accessible by the member.

        If the requested tag is on cooldown return `COOLDOWN.obj`, otherwise if no suggestions were found return None.
        """  # noqa: D205
        filtered_tags = [
            (ident, tag) for ident, tag in
            self.get_fuzzy_matches(tag_identifier)[:10]
            if tag.accessible_by(member)
        ]

        # Try exact match, includes checking through alt names
        tag = self.tags.get(tag_identifier)

        if tag is None and tag_identifier.group is not None:
            # Try exact match with only the name
            name_only_identifier = TagIdentifier(None, tag_identifier.group)
            tag = self.tags.get(name_only_identifier)
            if tag:
                # Ensure the correct tag information is sent to statsd
                tag_identifier = name_only_identifier

        if tag is None and len(filtered_tags) == 1:
            tag_identifier = filtered_tags[0][0]
            tag = filtered_tags[0][1]

        if tag is not None:
            if tag.on_cooldown_in(channel):
                log.debug(f"Tag {str(tag_identifier)!r} is on cooldown.")
                return COOLDOWN.obj
            tag.set_cooldown_for(channel)

            self.bot.stats.incr(
                f"tags.usages"
                f"{'.' + tag_identifier.group.replace('-', '_') if tag_identifier.group else ''}"
                f".{tag_identifier.name.replace('-', '_')}"
            )
            return tag.embed

        if not filtered_tags:
            return None
        suggested_tags_text = "\n".join(
            f"**\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}** {identifier}"
            for identifier, tag in filtered_tags
            if not tag.on_cooldown_in(channel)
        )
        return Embed(
            title="Did you mean...",
            description=suggested_tags_text
        )

    def accessible_tags(self, member: Member) -> list[str]:
        """Return a formatted list of tags that are accessible by `member`; groups first, and alphabetically sorted."""
        def tag_sort_key(tag_item: tuple[TagIdentifier, Tag]) -> str:
            group, name = tag_item[0]
            if group is None:
                # Max codepoint character to force tags without a group to the end
                group = chr(0x10ffff)

            return group + name

        result_lines = []
        current_group = ""
        group_accessible = True

        for identifier, tag in sorted(self.tags.items(), key=tag_sort_key):

            if identifier.group != current_group:
                if not group_accessible:
                    # Remove group separator line if no tags in the previous group were accessible by the member.
                    result_lines.pop()
                # A new group began, add a separator with the group name.
                current_group = identifier.group
                if current_group is not None:
                    group_accessible = False
                    result_lines.append(f"\n\N{BULLET} **{current_group}**")
                else:
                    result_lines.append("\n")

            if tag.accessible_by(member):
                result_lines.append(f"**\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}** {identifier.name}")
                group_accessible = True

        return result_lines

    def accessible_tags_in_group(self, group: str, member: Member) -> list[str]:
        """Return a formatted list of tags in `group`, that are accessible by `member`."""
        return sorted(
            f"**\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}** {identifier}"
            for identifier, tag in self.tags.items()
            if identifier.group == group and tag.accessible_by(member)
        )

    async def get_command_ctx(
        self,
        ctx: Context,
        name: str
    ) -> bool:
        """
        Made specifically for `ErrorHandler().try_get_tag` to handle sending tags through ctx.

        See `get_command` for more info, but here name is not optional unlike `get_command`.
        """
        identifier = TagIdentifier.from_string(name)

        if identifier.group is None:
            # Try to find accessible tags from a group matching the identifier's name.
            if group_tags := self.accessible_tags_in_group(identifier.name, ctx.author):
                await LinePaginator.paginate(
                    group_tags, ctx, Embed(title=f"Tags under *{identifier.name}*"), **self.PAGINATOR_DEFAULTS
                )
                return True

        embed = await self.get_tag_embed(ctx.author, ctx.channel, identifier)
        if embed is None:
            return False

        if embed is not COOLDOWN.obj:

            await wait_for_deletion(
                await ctx.send(embed=embed),
                (ctx.author.id,)
            )
        # A valid tag was found and was either sent, or is on cooldown
        return True

    @app_commands.command(name="tag")
    @app_commands.guild_only()
    async def get_command(self, interaction: Interaction, *, name: str | None) -> bool:
        """
        If a single argument matching a group name is given, list all accessible tags from that group
        Otherwise display the tag if one was found for the given arguments, or try to display suggestions for that name.

        With no arguments, list all accessible tags.

        Returns True if a message was sent, or if the tag is on cooldown.
        Returns False if no message was sent.
        """  # noqa: D205
        if not name:
            if self.tags:
                await LinePaginator.paginate(
                    self.accessible_tags(interaction.user),
                    interaction, Embed(title="Available tags"),
                    **self.PAGINATOR_DEFAULTS,
                )
            else:
                await interaction.response.send_message(embed=Embed(description="**There are no tags!**"))
            return True

        identifier = TagIdentifier.from_string(name)

        if identifier.group is None:
            # Try to find accessible tags from a group matching the identifier's name.
            if group_tags := self.accessible_tags_in_group(identifier.name, interaction.user):
                await LinePaginator.paginate(
                    group_tags, interaction, Embed(title=f"Tags under *{identifier.name}*"), **self.PAGINATOR_DEFAULTS
                )
                return True

        embed = await self.get_tag_embed(interaction.user, interaction.channel, identifier)
        ephemeral = False
        if embed is None:
            description = f"**There are no tags matching the name {name!r}!**"
            embed = Embed(description=description)
            ephemeral = True
        elif embed is COOLDOWN.obj:
            description = f"Tag {name!r} is on cooldown."
            embed = Embed(description=description)
            ephemeral = True

        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        if not ephemeral:
            await wait_for_deletion(
                await interaction.original_response(),
                (interaction.user.id,)
            )

        # A valid tag was found and was either sent, or is on cooldown
        return True

    @get_command.autocomplete("name")
    async def name_autocomplete(
        self,
        interaction: Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocompleter for `/tag get` command."""
        names = [tag.name for tag in self.tags]
        choices = [
            app_commands.Choice(name=tag, value=tag)
            for tag in names if current.lower() in tag
        ]
        return choices[:25] if len(choices) > 25 else choices


async def setup(bot: Bot) -> None:
    """Load the Tags cog."""
    await bot.add_cog(Tags(bot))
