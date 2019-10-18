import logging
import time

from discord import Colour, Embed
from discord.ext.commands import Bot, Cog, Context, group

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


class Tags(Cog):
    """Save new tags and fetch existing tags."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.tag_cooldowns = {}

        self._cache = {}
        self._last_fetch = None

    async def _get_tags(self, is_forced: bool = False) -> None:
        """Getting all tags."""
        # Refresh only when there's a more than 5m gap from last call.
        if is_forced or not self._last_fetch or time.time() - self._last_fetch > 5 * 60:
            tags = await self.bot.api_client.get('bot/tags')
            self._cache = {tag['title'].lower(): tag for tag in tags}

    @staticmethod
    def _fuzzy_search(search: str, target: str) -> bool:
        found = 0
        index = 0
        _search = search.lower().replace(' ', '')
        _target = target.lower().replace(' ', '')
        for letter in _search:
            index = _target.find(letter, index)
            if index == -1:
                break
            found += index > 0
        return found / len(_search) * 100

    def _get_suggestions(self, tag_name: str, score: int) -> list:
        return sorted(
            (tag for tag in self._cache.values() if Tags._fuzzy_search(tag_name, tag['title']) >= score),
            key=lambda tag: Tags._fuzzy_search(tag_name, tag['title']),
            reverse=True
        )

    async def _get_tag(self, tag_name: str) -> list:
        """Get a specific tag."""
        await self._get_tags()
        found = [self._cache.get(tag_name.lower(), None)]
        if not found[0]:
            return self._get_suggestions(tag_name, 100) or self._get_suggestions(tag_name, 80)
        return found

    @group(name='tags', aliases=('tag', 't'), invoke_without_command=True)
    async def tags_group(self, ctx: Context, *, tag_name: TagNameConverter = None) -> None:
        """Show all known tags, a single tag, or run a subcommand."""
        await ctx.invoke(self.get_command, tag_name=tag_name)

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
                and (now - self.tag_cooldowns[tag_name]["time"]) < Cooldowns.tags
                and self.tag_cooldowns[tag_name]["channel"] == ctx.channel.id
            )

            if cooldown_conditions:
                return True
            return False

        if _command_on_cooldown(tag_name):
            time_left = Cooldowns.tags - (time.time() - self.tag_cooldowns[tag_name]["time"])
            log.warning(f"{ctx.author} tried to get the '{tag_name}' tag, but the tag is on cooldown. "
                        f"Cooldown ends in {time_left:.1f} seconds.")
            return

        await self._get_tags()

        if tag_name is not None:
            # tag = await self.bot.api_client.get(f'bot/tags/{tag_name}')
            founds = await self._get_tag(tag_name)

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
            # tags = await self.bot.api_client.get('bot/tags')
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
                    footer_text="To show a tag, type !tags <tagname>.",
                    empty=False,
                    max_lines=15
                )

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
    """Tags cog load."""
    bot.add_cog(Tags(bot))
    log.info("Cog loaded: Tags")
