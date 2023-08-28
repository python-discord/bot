import asyncio
import datetime
import difflib
import json
import random
from functools import partial

from discord import ButtonStyle, Colour, Embed, HTTPException, Interaction
from discord.abc import GuildChannel
from discord.ext import tasks
from discord.ext.commands import Cog, Context, group, has_any_role
from discord.ui import Button, View
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils.channel import get_or_fetch_channel

from bot.bot import Bot
from bot.constants import Bot as BotConfig, Channels, MODERATION_ROLES, NEGATIVE_REPLIES
from bot.converters import OffTopicName
from bot.log import get_logger
from bot.pagination import LinePaginator

CHANNELS = (Channels.off_topic_0, Channels.off_topic_1, Channels.off_topic_2)

# In case, the off-topic channel name format is modified.
OTN_FORMATTER = "ot{number}-{name}"
OT_NUMBER_INDEX = 2
NAME_START_INDEX = 4
MAX_RENAME_ATTEMPTS = 3

log = get_logger(__name__)


class OffTopicNames(Cog):
    """Commands related to managing the off-topic category channel names."""

    def __init__(self, bot: Bot):
        self.bot = bot

        # What errors to handle and restart the task using an exponential back-off algorithm
        self.update_names.add_exception_type(ResponseCodeError)
        self.update_names.start()

    async def cog_unload(self) -> None:
        """
        Gracefully stop the update_names task.

        Clear the exception types first, so that if the task hits any errors it is not re-attempted.
        """
        self.update_names.clear_exception_types()
        self.update_names.stop()

    async def _fetch_ot_names(self, count: int) -> list[str]:
        try:
            return await self.bot.api_client.get(
                "bot/off-topic-channel-names", params={"random_items": count}
            )
        except ResponseCodeError as e:
            log.error(f"Failed to get new off-topic channel names: code {e.response.status}")
            raise

    @tasks.loop(time=datetime.time(), reconnect=True)
    async def update_names(self) -> None:
        """Background updater task that performs the daily channel name update."""
        await self.bot.wait_until_guild_available()

        ot_channels = [await get_or_fetch_channel(self.bot, channel) for channel in CHANNELS]
        num_ot_channels = len(CHANNELS)

        channel_name_pool = iter(await self._fetch_ot_names(num_ot_channels))

        renamed_ot_channels: set[int] = set()
        deactivated_ot_names: list[str] = []

        for ot_channel in ot_channels:
            attempt = 0
            while attempt < MAX_RENAME_ATTEMPTS:
                attempt += 1
                try:
                    new_channel_name = next(channel_name_pool)
                except StopIteration:
                    mod_meta = await get_or_fetch_channel(self.bot, Channels.mod_meta)
                    await mod_meta.send(
                        f":x: The pool of off-topic names ran out whilst attempting to rename {ot_channel.mention}.\n"
                    )
                    break
                try:
                    log.debug(
                        f"Attempt #{attempt} / {MAX_RENAME_ATTEMPTS} to rename "
                        f"#{ot_channel.name} to #{new_channel_name}"
                    )
                    await ot_channel.update(name=new_channel_name)
                    log.debug(f"Successfully updated off-topic name #{ot_channel.name} to #{new_channel_name}")
                except HTTPException as e:
                    # We need to handle code 50035 ("invalid form body"),
                    # which we get when the new channel name isn't allowed.
                    #
                    # For more information see https://github.com/python-discord/bot/issues/2500
                    if (e.code != 50035):
                        # The error isn't the one we want to handle so re-raise
                        log.error(f"Failed to rename #{ot_channel.name} to #{new_channel_name}")
                        raise

                    # Deactivate the name since it's not valid
                    log.info(
                        f"Failed to rename #{ot_channel.name} to #{new_channel_name} as it's not "
                        "a valid name for servers in Server Discovery so removing it from the rota."
                    )
                    await self.bot.api_client.patch(
                        f"bot/off-topic-channel-names/{new_channel_name}",
                        data={"active": False}
                    )
                    deactivated_ot_names.append(new_channel_name)
                    log.debug(f"Successfully removed {new_channel_name} from the pool of off-topic channel names.")

                    # Add a replacement off-topic channel name to the pool
                    channel_name_pool = iter([*channel_name_pool, *await self._fetch_ot_names(1)])
                else:
                    renamed_ot_channels.add(ot_channel.id)
                    break

        if deactivated_ot_names:
            failed_to_rename = [ot_channel for ot_channel in ot_channels if ot_channel.id not in renamed_ot_channels]
            await self.handle_failed_renames(self.bot, deactivated_ot_names, failed_to_rename)

    @staticmethod
    async def handle_failed_renames(
        bot: Bot,
        deactivated_names: list[str],
        ot_channels_not_renamed: list[GuildChannel]
    ) -> None:
        """Sends an appropriate warning/error message to mod-meta for each ot channel that had a failed rename."""
        num_failures = len(deactivated_names)

        # Handle pluralisations
        if num_failures == 1:
            name_or_names = "name"
            its_or_theyre = "it's"
            deactivated_names_joined = f"`{deactivated_names[0]}`"
        else:
            name_or_names = "names"
            its_or_theyre = "they're"
            deactivated_names_joined = (
                ", ".join(f"`{name}`" for name in deactivated_names[:-1]) +
                f" and `{deactivated_names[-1]}`"
            )

        message = (
            f":warning: The following {num_failures} off-topic channel {name_or_names} failed, as {its_or_theyre}"
            f"not valid for servers in Server Discovery: {deactivated_names_joined}."
        )
        if num_ot_channels_not_renamed := len(ot_channels_not_renamed):
            if num_ot_channels_not_renamed == 1:
                ot_channels_not_renamed = ot_channels_not_renamed[0].mention
            else:
                ot_channels_not_renamed_joined = (
                    ", ".join(ot_channel.mention for ot_channel in ot_channels_not_renamed[:-1]) +
                    f" and {ot_channels_not_renamed[-1].mention}"
                )
            message += (
                f"\n:x: Was unable to rename {ot_channels_not_renamed_joined} "
                f"within the configured maximum {MAX_RENAME_ATTEMPTS} attempts."
            )

        mod_meta_channel = await get_or_fetch_channel(bot, Channels.mod_meta)
        await mod_meta_channel.send(message)

    async def toggle_ot_name_activity(self, ctx: Context, name: str, active: bool) -> None:
        """Toggle active attribute for an off-topic name."""
        data = {
            "active": active
        }
        await self.bot.api_client.patch(f"bot/off-topic-channel-names/{name}", data=data)
        await ctx.send(f"Off-topic name `{name}` has been {'activated' if active else 'deactivated'}.")

    async def list_ot_names(self, ctx: Context, active: bool = True) -> None:
        """Send an embed containing active/deactivated off-topic channel names."""
        result = await self.bot.api_client.get("bot/off-topic-channel-names", params={"active": json.dumps(active)})
        lines = sorted(f"• {name}" for name in result)
        embed = Embed(
            title=f"{'Active' if active else 'Deactivated'} off-topic names (`{len(result)}` total)",
            colour=Colour.blue()
        )
        if result:
            await LinePaginator.paginate(lines, ctx, embed, max_size=400, empty=False)
        else:
            embed.description = "Hmmm, seems like there's nothing here yet."
            await ctx.send(embed=embed)

    @group(name="otname", aliases=("otnames", "otn"), invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def otname_group(self, ctx: Context) -> None:
        """Add or list items from the off-topic channel name rotation."""
        await ctx.send_help(ctx.command)

    @otname_group.command(name="add", aliases=("a",))
    @has_any_role(*MODERATION_ROLES)
    async def add_command(self, ctx: Context, *, name: OffTopicName) -> None:
        """
        Adds a new off-topic name to the rotation.

        The name is not added if it is too similar to an existing name.
        """
        existing_names = await self.bot.api_client.get("bot/off-topic-channel-names")
        close_match = difflib.get_close_matches(name, existing_names, n=1, cutoff=0.8)

        if close_match:
            match = close_match[0]
            log.info(
                f"{ctx.author} tried to add channel name '{name}' but it was too similar to '{match}'"
            )
            await ctx.send(
                f":x: The channel name `{name}` is too similar to `{match}`, and thus was not added. "
                f"Use `{BotConfig.prefix}otn forceadd` to override this check."
            )
        else:
            await self._add_name(ctx, name)

    @otname_group.command(name="forceadd", aliases=("fa",))
    @has_any_role(*MODERATION_ROLES)
    async def force_add_command(self, ctx: Context, *, name: OffTopicName) -> None:
        """Forcefully adds a new off-topic name to the rotation."""
        await self._add_name(ctx, name)

    async def _add_name(self, ctx: Context, name: str) -> None:
        """Adds an off-topic channel name to the site storage."""
        await self.bot.api_client.post("bot/off-topic-channel-names", params={"name": name})

        log.info(f"{ctx.author} added the off-topic channel name '{name}'")
        await ctx.send(f":ok_hand: Added `{name}` to the names list.")

    @otname_group.command(name="delete", aliases=("remove", "rm", "del", "d"))
    @has_any_role(*MODERATION_ROLES)
    async def delete_command(self, ctx: Context, *, name: OffTopicName) -> None:
        """Removes a off-topic name from the rotation."""
        await self.bot.api_client.delete(f"bot/off-topic-channel-names/{name}")

        log.info(f"{ctx.author} deleted the off-topic channel name '{name}'")
        await ctx.send(f":ok_hand: Removed `{name}` from the names list.")

    @otname_group.command(name="activate", aliases=("whitelist",))
    @has_any_role(*MODERATION_ROLES)
    async def activate_ot_name(self, ctx: Context, name: OffTopicName) -> None:
        """Activate an existing off-topic name."""
        await self.toggle_ot_name_activity(ctx, name, True)

    @otname_group.command(name="deactivate", aliases=("blacklist",))
    @has_any_role(*MODERATION_ROLES)
    async def de_activate_ot_name(self, ctx: Context, name: OffTopicName) -> None:
        """Deactivate a specific off-topic name."""
        await self.toggle_ot_name_activity(ctx, name, False)

    @otname_group.command(name="reroll")
    @has_any_role(*MODERATION_ROLES)
    async def re_roll_command(self, ctx: Context, ot_channel_index: int | None = None) -> None:
        """
        Re-roll an off-topic name for a specific off-topic channel and deactivate the current name.

        ot_channel_index: [0, 1, 2, ...]
        """
        if ot_channel_index is not None:
            try:
                channel = self.bot.get_channel(CHANNELS[ot_channel_index])
            except IndexError:
                await ctx.send(f":x: No off-topic channel found with index {ot_channel_index}.")
                return
        elif ctx.channel.id in CHANNELS:
            channel = ctx.channel

        else:
            await ctx.send("Please specify channel for which the off-topic name should be re-rolled.")
            return

        old_channel_name = channel.name
        old_ot_name = old_channel_name[NAME_START_INDEX:]  # ot1-name-of-ot -> name-of-ot

        await self.de_activate_ot_name(ctx, old_ot_name)

        response = await self.bot.api_client.get(
            "bot/off-topic-channel-names", params={"random_items": 1}
        )
        try:
            new_channel_name = response[0]
        except IndexError:
            await ctx.send("Out of active off-topic names. Add new names to reroll.")
            return

        async def rename_channel() -> None:
            """Rename off-topic channel and log events."""
            await channel.edit(
                name=OTN_FORMATTER.format(number=old_channel_name[OT_NUMBER_INDEX], name=new_channel_name)
            )
            log.info(
                f"{ctx.author} Off-topic channel re-named from `{old_ot_name}` "
                f"to `{new_channel_name}`."
            )

            await ctx.message.reply(
                f":ok_hand: Off-topic channel re-named from `{old_ot_name}` "
                f"to `{new_channel_name}`. "
            )

        try:
            await asyncio.wait_for(rename_channel(), 3)
        except asyncio.TimeoutError:
            # Channel rename endpoint rate limited. The task was cancelled by asyncio.
            btn_yes = Button(label="Yes", style=ButtonStyle.success)
            btn_no = Button(label="No", style=ButtonStyle.danger)

            embed = Embed(
                title=random.choice(NEGATIVE_REPLIES),
                description=(
                    "Re-naming the channel is being rate-limited. "
                    "Would you like to schedule an asyncio task to rename the channel within the current bot session ?"
                ),
                colour=Colour.blurple()
            )

            async def btn_call_back(schedule: bool, interaction: Interaction) -> None:
                if ctx.author != interaction.user:
                    log.info("User is not author, skipping.")
                    return
                message = interaction.message

                embed.description = (
                    "Scheduled a channel re-name process within the current bot session."
                    if schedule
                    else
                    "Channel not re-named due to rate limit. Please try again later."
                )
                await message.edit(embed=embed, view=None)

                if schedule:
                    await rename_channel()

            btn_yes.callback = partial(btn_call_back, True)
            btn_no.callback = partial(btn_call_back, False)

            view = View()
            view.add_item(btn_yes)
            view.add_item(btn_no)

            await ctx.message.reply(embed=embed, view=view)

    @otname_group.group(name="list", aliases=("l",), invoke_without_command=True)
    @has_any_role(*MODERATION_ROLES)
    async def list_command(self, ctx: Context) -> None:
        """
        Lists all currently known off-topic channel names in a paginator.

        Restricted to Moderator and above to not spoil the surprise.
        """
        await self.active_otnames_command(ctx)

    @list_command.command(name="active", aliases=("a",))
    @has_any_role(*MODERATION_ROLES)
    async def active_otnames_command(self, ctx: Context) -> None:
        """List active off-topic channel names."""
        await self.list_ot_names(ctx, True)

    @list_command.command(name="deactivated", aliases=("d",))
    @has_any_role(*MODERATION_ROLES)
    async def deactivated_otnames_command(self, ctx: Context) -> None:
        """List deactivated off-topic channel names."""
        await self.list_ot_names(ctx, False)

    @otname_group.command(name="search", aliases=("s",))
    @has_any_role(*MODERATION_ROLES)
    async def search_command(self, ctx: Context, *, query: OffTopicName) -> None:
        """Search for an off-topic name."""
        query = OffTopicName.translate_name(query, from_unicode=False).lower()

        # Map normalized names to returned names for search purposes
        result = {
            OffTopicName.translate_name(name, from_unicode=False).lower(): name
            for name in await self.bot.api_client.get("bot/off-topic-channel-names")
        }

        # Search normalized keys
        in_matches = {name for name in result if query in name}
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


async def setup(bot: Bot) -> None:
    """Load the OffTopicNames cog."""
    await bot.add_cog(OffTopicNames(bot))
