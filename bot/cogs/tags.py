import logging
import re
import time
from typing import Dict, List, Optional

from discord import Colour, Embed
from discord.ext.commands import Cog, Context, group

from bot.bot import Bot
from bot.constants import Channels, Cooldowns, MODERATION_ROLES, Roles
from bot.converters import TagContentConverter, TagNameConverter
from bot.decorators import with_role
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)

TEST_CHANNELS = (
    Channels.devtest,
    Channels.bot,
    Channels.helpers
)

REGEX_NON_ALPHABET = re.compile(r"[^a-z]", re.MULTILINE & re.IGNORECASE)


class Tags(Cog):
    """Save new tags and fetch existing tags."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.tag_cooldowns = {}

        self._cache = {}
        self._last_fetch: float = 0.0

    async def _get_tags(self, is_forced: bool = False) -> None:
        """Get all tags."""
        # refresh only when there's a more than 5m gap from last call.
        time_now: float = time.time()
        if is_forced or not self._last_fetch or time_now - self._last_fetch > 5 * 60:
            tags = await self.bot.api_client.get('bot/tags')
            self._cache = {tag['title'].lower(): tag for tag in tags}
            self._last_fetch = time_now

    @staticmethod
    def _fuzzy_search(search: str, target: str) -> int:
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

    async def _get_tag(self, tag_name: str) -> list:
        """Get a specific tag."""
        await self._get_tags()
        found = [self._cache.get(tag_name.lower(), None)]
        if not found[0]:
            return self._get_suggestions(tag_name)
        return found

    @group(name='tags', aliases=('tag', 't'), invoke_without_command=True)
    async def tags_group(self, ctx: Context, *, tag_name: TagNameConverter = None) -> None:
        """Show all known tags, a single tag, or run a subcommand."""
        await ctx.invoke(self.get_command, tag_name=tag_name)

    def command_on_cooldown(self, ctx: Context, tag_name: str) -> bool:
        """
        Check if the command is currently on cooldown, on a per-tag, per-channel basis.

        The cooldown duration is set in constants.py.
        """
        now = time.time()

        cooldown_conditions = (
            tag_name
            and tag_name in self.tag_cooldowns
            and (now - self.tag_cooldowns[tag_name]["time"]) < Cooldowns.tags
            and self.tag_cooldowns[tag_name]["channel"] == ctx.channel.id
        )

        if cooldown_conditions:
            return True
        return False

    async def display_tag(self, ctx: Context, tag_name: str = None) -> bool:
        """
        Show contents of the tag `tag_name` in `ctx` and return True if something is shown.

        If a tag is not found, display similar tag names as suggestions. If a tag is not specified,
        display a paginated embed of all tags.

        Tags are on cooldowns on a per-tag, per-channel basis. If a tag is on cooldown, display
        nothing and return False.
        """
        if self.command_on_cooldown(ctx, tag_name):
            time_left = Cooldowns.tags - (time.time() - self.tag_cooldowns[tag_name]["time"])
            log.warning(f"{ctx.author} tried to get the '{tag_name}' tag, but the tag is on cooldown. "
                        f"Cooldown ends in {time_left:.1f} seconds.")
            return False

        await self._get_tags()

        if tag_name is not None:
            founds = await self._get_tag(tag_name)

            if len(founds) == 1:
                tag = founds[0]
                if ctx.channel.id not in TEST_CHANNELS:
                    self.tag_cooldowns[tag_name] = {
                        "time": time.time(),
                        "channel": ctx.channel.id
                    }
                await ctx.send(embed=Embed.from_dict(tag['embed']))
                return True
            elif founds and len(tag_name) >= 3:
                await ctx.send(embed=Embed(
                    title='Did you mean ...',
                    description='\n'.join(tag['title'] for tag in founds[:10])
                ))
                return True

        else:
            tags = self._cache.values()
            if not tags:
                await ctx.send(embed=Embed(
                    description="**There are no tags in the database!**",
                    colour=Colour.red()
                ))
                return True
            else:
                embed: Embed = Embed(title="**Current tags**")
                await LinePaginator.paginate(
                    sorted(f"**»**   {tag['title']}" for tag in tags),
                    ctx,
                    embed,
                    footer_text="To show a tag, type !tags <tagname>.",
                    empty=False,
                    max_lines=15
                )
                return True

        return False

    @tags_group.command(name='get', aliases=('show', 'g'))
    async def get_command(self, ctx: Context, *, tag_name: TagNameConverter = None) -> None:
        """Get a specified tag, or a list of all tags if no tag is specified."""
        await self.display_tag(ctx, tag_name)

    @tags_group.command(name='set', aliases=('add', 's'))
    @with_role(*MODERATION_ROLES)
    async def set_command(
        self,
        ctx: Context,
        tag_name: TagNameConverter,
        *,
        tag_content: TagContentConverter,
    ) -> None:
        """Create a new tag."""
        body = {
            'title': tag_name.lower().strip(),
            'embed': {
                'title': tag_name,
                'description': tag_content
            }
        }

        await self.bot.api_client.post('bot/tags', json=body)
        self._cache[tag_name.lower()] = await self.bot.api_client.get(f'bot/tags/{tag_name}')

        log.debug(f"{ctx.author} successfully added the following tag to our database: \n"
                  f"tag_name: {tag_name}\n"
                  f"tag_content: '{tag_content}'\n")

        await ctx.send(embed=Embed(
            title="Tag successfully added",
            description=f"**{tag_name}** added to tag database.",
            colour=Colour.blurple()
        ))

    @tags_group.command(name='edit', aliases=('e', ))
    @with_role(*MODERATION_ROLES)
    async def edit_command(
        self,
        ctx: Context,
        tag_name: TagNameConverter,
        *,
        tag_content: TagContentConverter,
    ) -> None:
        """Edit an existing tag."""
        body = {
            'embed': {
                'title': tag_name,
                'description': tag_content
            }
        }

        await self.bot.api_client.patch(f'bot/tags/{tag_name}', json=body)
        self._cache[tag_name.lower()] = await self.bot.api_client.get(f'bot/tags/{tag_name}')

        log.debug(f"{ctx.author} successfully edited the following tag in our database: \n"
                  f"tag_name: {tag_name}\n"
                  f"tag_content: '{tag_content}'\n")

        await ctx.send(embed=Embed(
            title="Tag successfully edited",
            description=f"**{tag_name}** edited in the database.",
            colour=Colour.blurple()
        ))

    @tags_group.command(name='delete', aliases=('remove', 'rm', 'd'))
    @with_role(Roles.admin, Roles.owner)
    async def delete_command(self, ctx: Context, *, tag_name: TagNameConverter) -> None:
        """Remove a tag from the database."""
        await self.bot.api_client.delete(f'bot/tags/{tag_name}')
        self._cache.pop(tag_name.lower(), None)

        log.debug(f"{ctx.author} successfully deleted the tag called '{tag_name}'")
        await ctx.send(embed=Embed(
            title=tag_name,
            description=f"Tag successfully removed: {tag_name}.",
            colour=Colour.blurple()
        ))


def setup(bot: Bot) -> None:
    """Load the Tags cog."""
    bot.add_cog(Tags(bot))
