import asyncio
import logging
from datetime import datetime, timedelta

from discord import Colour, Embed
from discord.ext.commands import BadArgument, Bot, Context, Converter, command

from bot.constants import Channels, Keys, Roles, URLs
from bot.decorators import with_role
from bot.pagination import LinePaginator


CHANNELS = (Channels.off_topic_0, Channels.off_topic_1, Channels.off_topic_2)
log = logging.getLogger(__name__)


class OffTopicName(Converter):
    """A converter that ensures an added off-topic name is valid."""

    @staticmethod
    async def convert(ctx: Context, argument: str):
        if not (2 <= len(argument) <= 96):
            raise BadArgument("Channel name must be between 2 and 96 chars long")

        elif not all(c.isalpha() or c == '-' for c in argument):
            raise BadArgument(
                "Channel name must only consist of"
                " alphabetic characters or minus signs"
            )

        elif not argument.islower():
            raise BadArgument("Channel name must be lowercase")

        return argument


async def update_names(bot: Bot, headers: dict):
    """
    The background updater task that performs a channel name update daily.

    Args:
        bot (Bot):
            The running bot instance, used for fetching data from the
            website via the bot's `http_session`.
    """

    while True:
        today_at_midnight = datetime.utcnow().replace(microsecond=0, second=0, minute=0, hour=0)
        next_midnight = today_at_midnight + timedelta(days=1)
        seconds_to_sleep = (next_midnight - datetime.utcnow()).seconds
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
            self.updater_task = await self.bot.loop.create_task(coro)

    @command(name='otname.add()', aliases=['otname.add'])
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def otname_add(self, ctx, name: OffTopicName):
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

    @command(name='otname.list()', aliases=['otname.list'])
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def otname_list(self, ctx):
        """
        Lists all currently known off-topic channel names in a paginator.
        Restricted to Moderator and above to not spoil the surprise.
        """

        result = await self.bot.http_session.get(
            URLs.site_off_topic_names_api,
            headers=self.headers
        )
        response = await result.json()

        embed = Embed(
            title=f"Known off-topic names (`{len(response)}` total)",
            colour=Colour.blue()
        )
        await LinePaginator.paginate(
            sorted(response),
            ctx,
            embed,
            max_size=400,
            empty=False
        )


def setup(bot: Bot):
    bot.add_cog(OffTopicNames(bot))
    log.info("Cog loaded: OffTopicNames")
