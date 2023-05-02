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

from bot.bot import Bot
from bot.constants import Bot as BotConfig, Channels, MODERATION_ROLES, NEGATIVE_REPLIES
from bot.converters import OffTopicName
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils.channel import get_or_fetch_channel

CHANNELS = (Channels.off_topic_0, Channels.off_topic_1, Channels.off_topic_2)

# In case, the off-topic channel name format is modified.
OTN_FORMATTER = "ot{number}-{name}"
OT_NUMBER_INDEX = 2
NAME_START_INDEX = 4
MAX_RENAME_ATTEMPTS = 3
RENAME_WARNING_TEMPLATE = (
    ":warning: There {was_or_were} {num_failures} {failure_or_failures} when attempting to rename ot{number}, as "
    "{names} {is_or_are} invalid channel {name_or_names} for servers in Server Discovery.\n"
    ":white_check_mark: Attempt #{success_attempt} / {max_attempts} succeeded in renaming ot{number} to {new_name}."
)

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

    @tasks.loop(time=datetime.time(), reconnect=True)
    async def update_names(self) -> None:
        """Background updater task that performs the daily channel name update."""
        await self.bot.wait_until_guild_available()

        channels = [await get_or_fetch_channel(channel_id) for channel_id in CHANNELS]
        failed_renames = {}
        successfully_renamed = set()
        for attempt in range(MAX_RENAME_ATTEMPTS):
            # Get the necessary amount of new channel names
            remaining_channels = set(channel.id for channel in channels if channel.id not in successfully_renamed)
            try:
                num_names_to_fetch = len(remaining_channels)
                new_channel_names: list = await self.bot.api_client.get(
                    "bot/off-topic-channel-names", params={"random_items": num_names_to_fetch}
                )
                if (num_fetched := len(new_channel_names)) < num_names_to_fetch:
                    # Handle when there's not enough names in the pool
                    log.warn(
                        f"Attempted to fetch {num_names_to_fetch} off-topic names but "
                        f"only received {num_fetched} so not updating any off-topic names."
                    )
                    if failed_renames:
                        # Make sure we still notify of any previous rename failures
                        await self.handle_failed_renames(failed_renames, channels)
                    return
                new_channel_names = iter(new_channel_names)
            except ResponseCodeError as e:
                log.error(f"Failed to get new off-topic channel names: code {e.response.status}")
                raise

            # Attempt to rename remaining channels using the acquired names.
            # NB: We loop of `channels` instead of `remaining_channels` to ensure
            # that the `channel_indx` is the same as the `number` to pass into `OTN_FORMATTER`
            for channel_indx, channel in enumerate(channels):
                if channel.id not in remaining_channels:
                    continue

                new_channel_name = next(new_channel_names)

                name_before = channel.name
                name_after = OTN_FORMATTER.format(number=channel_indx, name=new_channel_name)
                log.debug(
                    f"Attempt #{attempt + 1} / {MAX_RENAME_ATTEMPTS} is attempting to rename "
                    f"#{name_before} to #{name_after}"
                )
                try:
                    await channel.edit(name=name_after)
                    successfully_renamed.add(channel.id)
                    log.debug(f"Updated off-topic name #{name_before} to #{name_after}")
                except HTTPException as e:
                    # We need to handle code 50035 ("invalid form body"),
                    # which we get when the new channel name isn't allowed.
                    #
                    # For more information see https://github.com/python-discord/bot/issues/2500
                    if (e.code != 50035):
                        # The error isn't the one we want to handle so re-raise
                        raise e

                    failed_renames[channel_indx] = failed_renames.get(channel_indx, []) + [new_channel_name]
                    # Deactivate the name since it's not valid
                    log.info(
                        f"Deactiving off-topic name {new_channel_name} as "
                        "it's not a valid name for servers in Server Discovery"
                    )
                    await self.bot.api_client.patch(
                        f"bot/off-topic-channel-names/{new_channel_name}",
                        data={"active": False}
                    )

            if len(successfully_renamed) == len(channels):
                # All the channels have been successfully renamed
                break

        # Handle any rename failures
        if failed_renames:
            await self.handle_failed_renames(failed_renames, channels)

    @staticmethod
    async def handle_failed_renames(failed_renames: dict[int, list[str]], channels: list[GuildChannel]) -> None:
        """Sends an appropriate warning/error message to mod-meta for each ot channel that had a failed rename."""
        for channel_indx, failed_names in failed_renames.items():
            channel = channels[channel_indx]
            num_failures = len(failed_names)

            # Handle pluralisations
            if num_failures == 1:
                names = f"`{failed_names[0]}`"
                name_or_names = "name"
                is_or_are = "is an"
            else:
                names = f"{', '.join((f'`{name}`' for name in failed_names[:-1]))} and `{failed_names[-1]}`"
                name_or_names = "names"
                is_or_are = "are"

            if num_failures == MAX_RENAME_ATTEMPTS:
                # All attempts failed to rename the channel
                message = (
                    f":x: Failed to rename {channel.mention} as the attempted {name_or_names} "
                    f"({names}) {is_or_are} invalid channel {name_or_names} for servers in Server Discovery."
                )
            else:
                # Did eventually rename the channel, but there was at least
                # one failure so make sure we still notify in the mod-meta channel
                if num_failures == 1:
                    # Format warning template with singulars
                    was_or_were = "was"
                    failure_or_failures = "failure"
                else:
                    # Format warning template with plurals
                    was_or_were = "were"
                    failure_or_failures = "failures"

                message = RENAME_WARNING_TEMPLATE.format(
                    was_or_were=was_or_were,
                    num_failures=num_failures,
                    failure_or_failures=failure_or_failures,
                    number=channel_indx,
                    names=names,
                    is_or_are=is_or_are,
                    name_or_names=name_or_names,
                    success_attempt=num_failures + 1,
                    max_attempts=MAX_RENAME_ATTEMPTS,
                    new_name=channel.mention
                )

            mod_meta_channel = await get_or_fetch_channel(Channels.mod_meta)
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
