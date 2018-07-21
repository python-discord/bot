import json
import logging
import random

from discord import Embed, Message, User, Colour
from discord.ext.commands import Bot, Context, group

from bot.constants import Roles, Clean, URLs, Keys, NEGATIVE_REPLIES
from bot.decorators import with_role

log = logging.getLogger(__name__)


class Clean:

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}
        self.cleaning = False

    async def _upload_log(self, log_data):
        """
        Uploads the log data to the database via
        an API endpoint for uploading logs.

        Returns a URL that can be used to view the log.
        """

        response = await self.bot.http_session.post(
            URLs.site_clean_api,
            headers=self.headers,
            json={"log_data": log_data}
        )

        data = await response.json()
        log_id = data["log_id"]

        return f"{URLs.site_clean_logs}/{log_id}"

    async def _clean_messages(self, amount, channel, bots_only: bool=False, user: User=None):
        """
        A helper function that does the actual message cleaning.

        :param bots_only: Set this to True if you only want to delete bot messages.
        :param user: Specify a user and it will only delete messages by this user.
        :return: Returns an embed
        """

        # Is this an acceptable amount of messages to clean?
        if amount > Clean.message_limit:
            embed = Embed(
                color=Colour.red(),
                title=random.choice(NEGATIVE_REPLIES),
                description=f"You cannot clean more than {Clean.message_limit} messages."
            )
            return embed

        # Are we already performing a clean?
        if self.cleaning:
            embed = Embed(
                color=Colour.red(),
                title=random.choice(NEGATIVE_REPLIES),
                description="Multiple simultaneous cleaning processes is not allowed."
            )
            return embed

        # Skip the first message, as that will be the invocation
        history = channel.history(limit=amount)
        await history.next()

        message_log = []

        async for message in history:

            delete_condition = (
                bots_only and message.author.bot    # Delete bot messages
                or user and message.author == user  # Delete user messages
                or not bots_only and not user       # Delete all messages
            )

            if delete_condition:
                await message.delete()
                content = message.content or message.embeds[0].description
                author = f"{message.author.name}#{message.author.discriminator}"
                message_log.append({
                    "content": content,
                    "author": author,
                    "timestamp": message.created_at.strftime("%D %H:%M")
                })

        if message_log:
            # Reverse the list to restore chronological order
            message_log = list(reversed(message_log))
            upload_log = await self._upload_log(message_log)
        else:
            upload_log = "Naw, nothing there!"

        embed = Embed(
            description=upload_log
        )

        return embed

    @group(invoke_without_command=True, name="clean", hidden=True)
    @with_role(Roles.moderator, Roles.admin, Roles.owner)
    async def clean_group(self, ctx: Context):
        """
        Commands for cleaning messages in channels
        """

        await ctx.invoke(self.bot.get_command("help"), "clean")

    @clean_group.command(aliases=["user"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner)
    async def clean_user(self, ctx: Context, user: User, amount: int = 10):
        """
        Delete messages posted by the provided user,
        and stop cleaning after traversing `amount` messages.
        """

        embed = await self._clean_messages(amount, ctx.channel, user=user)

        await ctx.send(embed=embed)

    @clean_group.command(aliases=["all"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner)
    async def clean_all(self, ctx: Context, amount: int = 10):
        """
        Delete all messages, regardless of posted,
        and stop cleaning after traversing `amount` messages.
        """

        embed = await self._clean_messages(amount, ctx.channel)

        await ctx.send(embed=embed)

    @clean_group.command(aliases=["bots"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner)
    async def clean_bots(self, ctx: Context, amount: int = 10):
        """
        Delete all messages posted by a bot,
        and stop cleaning after traversing `amount` messages.
        """

        embed = await self._clean_messages(amount, ctx.channel, bots_only=True)

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Clean(bot))
    log.info("Cog loaded: Clean")
