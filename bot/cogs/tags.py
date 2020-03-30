import logging
import re
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from discord import Colour, Embed
from discord.ext.commands import Cog, Context, group

from bot import constants
from bot.bot import Bot
from bot.converters import TagNameConverter
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)

TEST_CHANNELS = (
    constants.Channels.bot_commands,
    constants.Channels.helpers
)

REGEX_NON_ALPHABET = re.compile(r"[^a-z]", re.MULTILINE & re.IGNORECASE)
FOOTER_TEXT = f"To show a tag, type {constants.Bot.prefix}tags <tagname>."


class Tags(Cog):
    """Save new tags and fetch existing tags."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.tag_cooldowns = {}
        self._cache = self.get_tags()

    @staticmethod
    def get_tags() -> dict:
        """Get all tags."""
        # Save all tags in memory.
        cache = {}
        tag_files = Path("bot", "resources", "tags").iterdir()
        for file in tag_files:
            tag_title = file.stem
            tag = {
                "title": tag_title,
                "embed": {
                    "description": file.read_text()
                }
            }
            cache[tag_title] = tag
        return cache

    @staticmethod
    def _fuzzy_search(search: str, target: str) -> float:
        """A simple scoring algorithm based on how many letters are found / total, with order in mind."""
        current, index = 0, 0
        _search = REGEX_NON_ALPHABET.sub('', search.lower())
        _targets = iter(REGEX_NON_ALPHABET.split(target.lower()))
        _target = next(_targets)
        try:
            while True:
                while index < len(_target) and _search[current] == _target[index]:
                    current += 1
                    index += 1
                index, _target = 0, next(_targets)
        except (StopIteration, IndexError):
            pass
        return current / len(_search) * 100

    def _get_suggestions(self, tag_name: str, thresholds: Optional[List[int]] = None) -> List[str]:
        """Return a list of suggested tags."""
        scores: Dict[str, int] = {
            tag_title: Tags._fuzzy_search(tag_name, tag['title'])
            for tag_title, tag in self._cache.items()
        }

        thresholds = thresholds or [100, 90, 80, 70, 60]

        for threshold in thresholds:
            suggestions = [
                self._cache[tag_title]
                for tag_title, matching_score in scores.items()
                if matching_score >= threshold
            ]
            if suggestions:
                return suggestions

        return []

    def _get_tag(self, tag_name: str) -> list:
        """Get a specific tag."""
        found = [self._cache.get(tag_name.lower(), None)]
        if not found[0]:
            return self._get_suggestions(tag_name)
        return found

    def _get_tags_via_content(self, check: Callable[[Iterable], bool], keywords: str) -> list:
        """
        Search for tags via contents.

        `predicate` will be the built-in any, all, or a custom callable. Must return a bool.
        """
        keywords_processed: List[str] = []
        for keyword in keywords.split(','):
            keyword_sanitized = keyword.strip().casefold()
            if not keyword_sanitized:
                # this happens when there are leading / trailing / consecutive comma.
                continue
            keywords_processed.append(keyword_sanitized)

        if not keywords_processed:
            # after sanitizing, we can end up with an empty list, for example when keywords is ','
            # in that case, we simply want to search for such keywords directly instead.
            keywords_processed = [keywords]

        matching_tags = []
        for tag in self._cache.values():
            if check(query in tag['embed']['description'].casefold() for query in keywords_processed):
                matching_tags.append(tag)

        return matching_tags

    async def _send_matching_tags(self, ctx: Context, keywords: str, matching_tags: list) -> None:
        """Send the result of matching tags to user."""
        if not matching_tags:
            pass
        elif len(matching_tags) == 1:
            await ctx.send(embed=Embed().from_dict(matching_tags[0]['embed']))
        else:
            is_plural = keywords.strip().count(' ') > 0 or keywords.strip().count(',') > 0
            embed = Embed(
                title=f"Here are the tags containing the given keyword{'s' * is_plural}:",
                description='\n'.join(tag['title'] for tag in matching_tags[:10])
            )
            await LinePaginator.paginate(
                sorted(f"**»**   {tag['title']}" for tag in matching_tags),
                ctx,
                embed,
                footer_text=FOOTER_TEXT,
                empty=False,
                max_lines=15
            )

    @group(name='tags', aliases=('tag', 't'), invoke_without_command=True)
    async def tags_group(self, ctx: Context, *, tag_name: TagNameConverter = None) -> None:
        """Show all known tags, a single tag, or run a subcommand."""
        await ctx.invoke(self.get_command, tag_name=tag_name)

    @tags_group.group(name='search', invoke_without_command=True)
    async def search_tag_content(self, ctx: Context, *, keywords: str) -> None:
        """
        Search inside tags' contents for tags. Allow searching for multiple keywords separated by comma.

        Only search for tags that has ALL the keywords.
        """
        matching_tags = self._get_tags_via_content(all, keywords)
        await self._send_matching_tags(ctx, keywords, matching_tags)

    @search_tag_content.command(name='any')
    async def search_tag_content_any_keyword(self, ctx: Context, *, keywords: Optional[str] = 'any') -> None:
        """
        Search inside tags' contents for tags. Allow searching for multiple keywords separated by comma.

        Search for tags that has ANY of the keywords.
        """
        matching_tags = self._get_tags_via_content(any, keywords or 'any')
        await self._send_matching_tags(ctx, keywords, matching_tags)

    @tags_group.command(name='get', aliases=('show', 'g'))
    async def get_command(self, ctx: Context, *, tag_name: TagNameConverter = None) -> None:
        """Get a specified tag, or a list of all tags if no tag is specified."""
        def _command_on_cooldown(tag_name: str) -> bool:
            """
            Check if the command is currently on cooldown, on a per-tag, per-channel basis.

            The cooldown duration is set in constants.py.
            """
            now = time.time()

            cooldown_conditions = (
                tag_name
                and tag_name in self.tag_cooldowns
                and (now - self.tag_cooldowns[tag_name]["time"]) < constants.Cooldowns.tags
                and self.tag_cooldowns[tag_name]["channel"] == ctx.channel.id
            )

            if cooldown_conditions:
                return True
            return False

        if _command_on_cooldown(tag_name):
            time_elapsed = time.time() - self.tag_cooldowns[tag_name]["time"]
            time_left = constants.Cooldowns.tags - time_elapsed
            log.info(
                f"{ctx.author} tried to get the '{tag_name}' tag, but the tag is on cooldown. "
                f"Cooldown ends in {time_left:.1f} seconds."
            )
            return

        if tag_name is not None:
            founds = self._get_tag(tag_name)

            if len(founds) == 1:
                tag = founds[0]
                if ctx.channel.id not in TEST_CHANNELS:
                    self.tag_cooldowns[tag_name] = {
                        "time": time.time(),
                        "channel": ctx.channel.id
                    }
                await ctx.send(embed=Embed.from_dict(tag['embed']))
            elif founds and len(tag_name) >= 3:
                await ctx.send(embed=Embed(
                    title='Did you mean ...',
                    description='\n'.join(tag['title'] for tag in founds[:10])
                ))

        else:
            tags = self._cache.values()
            if not tags:
                await ctx.send(embed=Embed(
                    description="**There are no tags in the database!**",
                    colour=Colour.red()
                ))
            else:
                embed: Embed = Embed(title="**Current tags**")
                await LinePaginator.paginate(
                    sorted(f"**»**   {tag['title']}" for tag in tags),
                    ctx,
                    embed,
                    footer_text=FOOTER_TEXT,
                    empty=False,
                    max_lines=15
                )


def setup(bot: Bot) -> None:
    """Load the Tags cog."""
    bot.add_cog(Tags(bot))
