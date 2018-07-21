import logging
import random

from discord import Colour, Embed, Message, User
from discord.ext.commands import Bot, Context, group

from bot.cogs.modlog import ModLog
from bot.constants import (
    Channels, CleanMessages, Icons,
    Keys, NEGATIVE_REPLIES, Roles, URLs
)
from bot.decorators import with_role

log = logging.getLogger(__name__)

COLOUR_RED = Colour(0xcd6d6d)


class Clean:

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-KEY": Keys.site_api}
        self.cleaning = False

    @property
    def mod_log(self) -> ModLog:
        return self.bot.get_cog("ModLog")

    async def _upload_log(self, log_data: list) -> str:
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

    async def _clean_messages(
            self, amount: int, ctx: Context,
            bots_only: bool=False, user: User=None
    ):
        """
        A helper function that does the actual message cleaning.

        :param bots_only: Set this to True if you only want to delete bot messages.
        :param user: Specify a user and it will only delete messages by this user.
        """

        # Bulk delete checks
        def predicate_bots_only(message: Message):
            return message.author.bot

        def predicate_specific_user(message: Message):
            return message.author == user

        # Is this an acceptable amount of messages to clean?
        if amount > CleanMessages.message_limit:
            embed = Embed(
                color=Colour.red(),
                title=random.choice(NEGATIVE_REPLIES),
                description=f"You cannot clean more than {CleanMessages.message_limit} messages."
            )
            await ctx.send(embed=embed)
            return

        # Are we already performing a clean?
        if self.cleaning:
            embed = Embed(
                color=Colour.red(),
                title=random.choice(NEGATIVE_REPLIES),
                description="Multiple simultaneous cleaning processes is not allowed."
            )
            await ctx.send(embed=embed)
            return

        # Look through the history and retrieve message data
        message_log = []
        message_ids = []

        self.cleaning = True

        async for message in ctx.channel.history(limit=amount):

            if not self.cleaning:
                return

            delete = (
                bots_only and message.author.bot    # Delete bot messages
                or user and message.author == user  # Delete user messages
                or not bots_only and not user       # Delete all messages
            )

            if delete and message.content or message.embeds:
                content = message.content or message.embeds[0].description
                author = f"{message.author.name}#{message.author.discriminator}"

                # Store the message data
                message_ids.append(message.id)
                message_log.append({
                    "content": content,
                    "author": author,
                    "timestamp": message.created_at.strftime("%D %H:%M")
                })

        self.cleaning = False

        # We should ignore the ID's we stored, so we don't get mod-log spam.
        self.mod_log.ignore_message_deletion(*message_ids)

        # Use bulk delete to actually do the cleaning. It's far faster.
        if bots_only:
            await ctx.channel.purge(
                limit=amount,
                check=predicate_bots_only,
            )
        elif user:
            await ctx.channel.purge(
                limit=amount,
                check=predicate_specific_user,
            )
        else:
            await ctx.channel.purge(
                limit=amount
            )

        # Reverse the list to restore chronological order
        if message_log:
            message_log = list(reversed(message_log))
            upload_log = await self._upload_log(message_log)
        else:
            # Can't build an embed, nothing to clean!
            embed = Embed(
                color=Colour.red(),
                description="No matching messages could be found."
            )
            await ctx.send(embed=embed)
            return

        # Build the embed and send it
        message = (
            f"**{len(message_ids)}** messages deleted in <#{ctx.channel.id}> by **{ctx.author.name}**\n\n"
            f"A log of the deleted messages can be found [here]({upload_log})."
        )

        embed = Embed(
            color=COLOUR_RED,
            description=message
        )

        embed.set_author(
            name=f"Bulk message delete",
            icon_url=Icons.message_bulk_delete
        )

        await self.bot.get_channel(Channels.modlog).send(embed=embed)

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

        await self._clean_messages(amount, ctx, user=user)

    @clean_group.command(aliases=["all"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner)
    async def clean_all(self, ctx: Context, amount: int = 10):
        """
        Delete all messages, regardless of posted,
        and stop cleaning after traversing `amount` messages.
        """

        await self._clean_messages(amount, ctx)

    @clean_group.command(aliases=["bots"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner)
    async def clean_bots(self, ctx: Context, amount: int = 10):
        """
        Delete all messages posted by a bot,
        and stop cleaning after traversing `amount` messages.
        """

        await self._clean_messages(amount, ctx, bots_only=True)

    @clean_group.command(aliases=["stop", "cancel", "abort"])
    @with_role(Roles.moderator, Roles.admin, Roles.owner)
    async def clean_cancel(self, ctx: Context):
        """
        If there is an ongoing cleaning process,
        attempt to immediately cancel it.
        """

        self.cleaning = False

        embed = Embed(
            color=Colour.blurple(),
            description="Clean interrupted."
        )
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Clean(bot))
    log.info("Cog loaded: Clean")
