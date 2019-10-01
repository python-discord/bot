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

        if tag_name is not None:
            tag = await self.bot.api_client.get(f'bot/tags/{tag_name}')
            if ctx.channel.id not in TEST_CHANNELS:
                self.tag_cooldowns[tag_name] = {
                    "time": time.time(),
                    "channel": ctx.channel.id
                }
            await ctx.send(embed=Embed.from_dict(tag['embed']))

        else:
            tags = await self.bot.api_client.get('bot/tags')
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

    @tags_group.command(name='set', aliases=('add', 'edit', 's'))
    @with_role(*MODERATION_ROLES)
    async def set_command(
        self,
        ctx: Context,
        tag_name: TagNameConverter,
        *,
        tag_content: TagContentConverter,
    ) -> None:
        """Create a new tag or update an existing one."""
        body = {
            'title': tag_name.lower().strip(),
            'embed': {
                'title': tag_name,
                'description': tag_content
            }
        }

        await self.bot.api_client.post('bot/tags', json=body)

        log.debug(f"{ctx.author} successfully added the following tag to our database: \n"
                  f"tag_name: {tag_name}\n"
                  f"tag_content: '{tag_content}'\n")

        await ctx.send(embed=Embed(
            title="Tag successfully added",
            description=f"**{tag_name}** added to tag database.",
            colour=Colour.blurple()
        ))

    @tags_group.command(name='delete', aliases=('remove', 'rm', 'd'))
    @with_role(Roles.admin, Roles.owner)
    async def delete_command(self, ctx: Context, *, tag_name: TagNameConverter) -> None:
        """Remove a tag from the database."""
        await self.bot.api_client.delete(f'bot/tags/{tag_name}')

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
