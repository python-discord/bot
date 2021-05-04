import difflib
import logging
from datetime import datetime, timedelta

from discord import Colour, Embed
from discord.ext.commands import Cog, Context, group, has_any_role
from discord.utils import sleep_until

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Channels, MODERATION_ROLES
from bot.converters import OffTopicName
from bot.pagination import LinePaginator

CHANNELS = (Channels.off_topic_0, Channels.off_topic_1, Channels.off_topic_2)
log = logging.getLogger(__name__)


async def update_names(bot: Bot) -> None:
    """Background updater task that performs the daily channel name update."""
    while True:
        # Since we truncate the compute timedelta to seconds, we add one second to ensure
        # we go past midnight in the `seconds_to_sleep` set below.
        today_at_midnight = datetime.utcnow().replace(microsecond=0, second=0, minute=0, hour=0)
        next_midnight = today_at_midnight + timedelta(days=1)
        await sleep_until(next_midnight)

        try:
            channel_0_name, channel_1_name, channel_2_name = await bot.api_client.get(
                'bot/off-topic-channel-names', params={'random_items': 3}
            )
        except ResponseCodeError as e:
            log.error(f"Failed to get new off topic channel names: code {e.response.status}")
            continue
        channel_0, channel_1, channel_2 = (bot.get_channel(channel_id) for channel_id in CHANNELS)

        await channel_0.edit(name=f'ot0-{channel_0_name}')
        await channel_1.edit(name=f'ot1-{channel_1_name}')
        await channel_2.edit(name=f'ot2-{channel_2_name}')
        log.debug(
            "Updated off-topic channel names to"
            f" {channel_0_name}, {channel_1_name} and {channel_2_name}"
        )


class OffTopicNames(Cog):
    """Commands related to managing the off-topic category channel names."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.updater_task = None

        self.bot.loop.create_task(self.init_offtopic_updater())

    def cog_unload(self) -> None:
        """Cancel any running updater tasks on cog unload."""
        if self.updater_task is not None:
            self.updater_task.cancel()

    async def init_offtopic_updater(self) -> None:
        """Start off-topic channel updating event loop if it hasn't already started."""
        await self.bot.wait_until_guild_available()
        if self.updater_task is None:
            coro = update_names(self.bot)
            self.updater_task = self.bot.loop.create_task(coro)

    @group(name='otname', aliases=('otnames', 'otn'), invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def otname_group(self, ctx: Context) -> None:
        """Add or list items from the off-topic channel name rotation."""
        await ctx.send_help(ctx.command)

    @otname_group.command(name='add', aliases=('a',))
    @has_any_role(*MODERATION_ROLES)
    async def add_command(self, ctx: Context, *, name: OffTopicName) -> None:
        """
        Adds a new off-topic name to the rotation.

        The name is not added if it is too similar to an existing name.
        """
        existing_names = await self.bot.api_client.get('bot/off-topic-channel-names')
        close_match = difflib.get_close_matches(name, existing_names, n=1, cutoff=0.8)

        if close_match:
            match = close_match[0]
            log.info(
                f"{ctx.author} tried to add channel name '{name}' but it was too similar to '{match}'"
            )
            await ctx.send(
                f":x: The channel name `{name}` is too similar to `{match}`, and thus was not added. "
                "Use `!otn forceadd` to override this check."
            )
        else:
            await self._add_name(ctx, name)

    @otname_group.command(name='forceadd', aliases=('fa',))
    @has_any_role(*MODERATION_ROLES)
    async def force_add_command(self, ctx: Context, *, name: OffTopicName) -> None:
        """Forcefully adds a new off-topic name to the rotation."""
        await self._add_name(ctx, name)

    async def _add_name(self, ctx: Context, name: str) -> None:
        """Adds an off-topic channel name to the site storage."""
        await self.bot.api_client.post('bot/off-topic-channel-names', params={'name': name})

        log.info(f"{ctx.author} added the off-topic channel name '{name}'")
        await ctx.send(f":ok_hand: Added `{name}` to the names list.")

    @otname_group.command(name='delete', aliases=('remove', 'rm', 'del', 'd'))
    @has_any_role(*MODERATION_ROLES)
    async def delete_command(self, ctx: Context, *, name: OffTopicName) -> None:
        """Removes a off-topic name from the rotation."""
        await self.bot.api_client.delete(f'bot/off-topic-channel-names/{name}')

        log.info(f"{ctx.author} deleted the off-topic channel name '{name}'")
        await ctx.send(f":ok_hand: Removed `{name}` from the names list.")

    @otname_group.command(name='list', aliases=('l',))
    @has_any_role(*MODERATION_ROLES)
    async def list_command(self, ctx: Context) -> None:
        """
        Lists all currently known off-topic channel names in a paginator.

        Restricted to Moderator and above to not spoil the surprise.
        """
        result = await self.bot.api_client.get('bot/off-topic-channel-names')
        lines = sorted(f"• {name}" for name in result)
        embed = Embed(
            title=f"Known off-topic names (`{len(result)}` total)",
            colour=Colour.blue()
        )
        if result:
            await LinePaginator.paginate(lines, ctx, embed, max_size=400, empty=False)
        else:
            embed.description = "Hmmm, seems like there's nothing here yet."
            await ctx.send(embed=embed)

    @otname_group.command(name='search', aliases=('s',))
    @has_any_role(*MODERATION_ROLES)
    async def search_command(self, ctx: Context, *, query: OffTopicName) -> None:
        """Search for an off-topic name."""
        query = OffTopicName.translate_name(query, from_unicode=False).lower()

        # Map normalized names to returned names for search purposes
        result = {
            OffTopicName.translate_name(name, from_unicode=False).lower(): name
            for name in await self.bot.api_client.get('bot/off-topic-channel-names')
        }

        # Search normalized keys
        in_matches = {name for name in result.keys() if query in name}
        close_matches = difflib.get_close_matches(query, result.keys(), n=10, cutoff=0.70)

        # Send Results
        lines = sorted(f"• {result[name]}" for name in in_matches.union(close_matches))
        embed = Embed(
            title="Query results",
            colour=Colour.blue()
        )

        if lines:
            await LinePaginator.paginate(lines, ctx, embed, max_size=400, empty=False)
        else:
            embed.description = "Nothing found."
            await ctx.send(embed=embed)


def setup(bot: Bot) -> None:
    """Load the OffTopicNames cog."""
    bot.add_cog(OffTopicNames(bot))
