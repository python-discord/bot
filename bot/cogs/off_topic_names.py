import asyncio
import logging
from datetime import datetime, timedelta

from discord import Colour, Embed
from discord.ext.commands import BadArgument, Bot, Context, Converter, group

from bot.constants import Channels, Keys, MODERATION_ROLES, URLs
from bot.decorators import with_role
from bot.pagination import LinePaginator


CHANNELS = (Channels.off_topic_0, Channels.off_topic_1, Channels.off_topic_2)
log = logging.getLogger(__name__)


class OffTopicName(Converter):
    """A converter that ensures an added off-topic name is valid."""

    @staticmethod
    async def convert(ctx: Context, argument: str):
        allowed_characters = ("-", "’", "'", "`")

        if not (2 <= len(argument) <= 96):
            raise BadArgument("Channel name must be between 2 and 96 chars long")

        elif not all(c.isalnum() or c in allowed_characters for c in argument):
            raise BadArgument(
                "Channel name must only consist of "
                "alphanumeric characters, minus signs or apostrophes."
            )

        elif not argument.islower():
            raise BadArgument("Channel name must be lowercase")

        # Replace some unusable apostrophe-like characters with "’".
        return argument.replace("'", "’").replace("`", "’")


async def update_names(bot: Bot, headers: dict):
    """
    The background updater task that performs a channel name update daily.

    Args:
        bot (Bot):
            The running bot instance, used for fetching data from the
            website via the bot's `http_session`.
    """

    while True:
        # Since we truncate the compute timedelta to seconds, we add one second to ensure
        # we go past midnight in the `seconds_to_sleep` set below.
        today_at_midnight = datetime.utcnow().replace(microsecond=0, second=0, minute=0, hour=0)
        next_midnight = today_at_midnight + timedelta(days=1)
        seconds_to_sleep = (next_midnight - datetime.utcnow()).seconds + 1
        await asyncio.sleep(seconds_to_sleep)

        response = await bot.http_session.get(
            f'{URLs.site_off_topic_names_api}?random_items=3',
            headers=headers
        )
        channel_0_name, channel_1_name, channel_2_name = await response.json()
        channel_0, channel_1, channel_2 = (bot.get_channel(channel_id) for channel_id in CHANNELS)

        await channel_0.edit(name=f'ot0-{channel_0_name}')
        await channel_1.edit(name=f'ot1-{channel_1_name}')
        await channel_2.edit(name=f'ot2-{channel_2_name}')
        log.debug(
            "Updated off-topic channel names to"
            f" {channel_0_name}, {channel_1_name} and {channel_2_name}"
        )


class OffTopicNames:
    """Commands related to managing the off-topic category channel names."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}
        self.updater_task = None

    def __cleanup(self):
        if self.updater_task is not None:
            self.updater_task.cancel()

    async def on_ready(self):
        if self.updater_task is None:
            coro = update_names(self.bot, self.headers)
            self.updater_task = self.bot.loop.create_task(coro)

    @group(name='otname', aliases=('otnames', 'otn'), invoke_without_command=True)
    @with_role(*MODERATION_ROLES)
    async def otname_group(self, ctx):
        """Add or list items from the off-topic channel name rotation."""

        await ctx.invoke(self.bot.get_command("help"), "otname")

    @otname_group.command(name='add', aliases=('a',))
    @with_role(*MODERATION_ROLES)
    async def add_command(self, ctx, name: OffTopicName):
        """Adds a new off-topic name to the rotation."""

        result = await self.bot.http_session.post(
            URLs.site_off_topic_names_api,
            headers=self.headers,
            params={'name': name}
        )

        response = await result.json()

        if result.status == 200:
            log.info(
                f"{ctx.author.name}#{ctx.author.discriminator}"
                f" added the off-topic channel name '{name}"
            )
            await ctx.send(":ok_hand:")
        else:
            error_reason = response.get('message', "No reason provided.")
            await ctx.send(f":warning: got non-200 from the API: {error_reason}")

    @otname_group.command(name='delete', aliases=('remove', 'rm', 'del', 'd'))
    @with_role(*MODERATION_ROLES)
    async def delete_command(self, ctx, name: OffTopicName):
        """Removes a off-topic name from the rotation."""

        result = await self.bot.http_session.delete(
            URLs.site_off_topic_names_api,
            headers=self.headers,
            params={'name': name}
        )

        response = await result.json()

        if result.status == 200:
            if response['deleted'] == 0:
                await ctx.send(f":warning: No name matching `{name}` was found in the database.")
            else:
                log.info(
                    f"{ctx.author.name}#{ctx.author.discriminator}"
                    f" deleted the off-topic channel name '{name}"
                )
                await ctx.send(":ok_hand:")
        else:
            error_reason = response.get('message', "No reason provided.")
            await ctx.send(f":warning: got non-200 from the API: {error_reason}")

    @otname_group.command(name='list', aliases=('l',))
    @with_role(*MODERATION_ROLES)
    async def list_command(self, ctx):
        """
        Lists all currently known off-topic channel names in a paginator.
        Restricted to Moderator and above to not spoil the surprise.
        """

        result = await self.bot.http_session.get(
            URLs.site_off_topic_names_api,
            headers=self.headers
        )
        response = await result.json()
        lines = sorted(f"• {name}" for name in response)

        embed = Embed(
            title=f"Known off-topic names (`{len(response)}` total)",
            colour=Colour.blue()
        )
        await LinePaginator.paginate(lines, ctx, embed, max_size=400, empty=False)


def setup(bot: Bot):
    bot.add_cog(OffTopicNames(bot))
    log.info("Cog loaded: OffTopicNames")
