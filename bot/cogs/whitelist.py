import logging

from discord import Colour, Embed
from discord.ext.commands import Bot, Cog, Context, group

from bot.constants import Roles
from bot.decorators import with_role
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)


class Whitelist(Cog):
    """Save new whitelists and fetch existing whitelist."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def _get_whitelisted_items(self, whitelist_type: str) -> list:
        """Returns the list of current whitelisted items for the type."""
        query_params = {"type": whitelist_type}
        result = await self.bot.api_client.get(f"bot/whitelist", params=query_params)
        whitelisted_items = [item["whitelisted_item"] for item in result]
        return whitelisted_items

    @group(name="whitelist", invoke_without_command=True)
    @with_role(Roles.owners, Roles.admins)
    async def whitelist_group(
        self, ctx: Context, whitelist_type: str, *, whitelist_item: str
    ) -> None:
        """Commands for managing your whitelist."""
        await ctx.invoke(
            self.set_command,
            whitelist_type=whitelist_type,
            whitelist_item=whitelist_item,
        )

    @whitelist_group.command(name="add", aliases=("append", "a"))
    @with_role(Roles.owners, Roles.admins)
    async def set_command(
        self, ctx: Context, whitelist_type: str, *, whitelist_item: str
    ) -> None:
        """Add a new item to the whitelist for the whitelist_type."""
        whitelist_type, whitelist_item = (
            whitelist_type.lower().strip(),
            whitelist_item.strip(),
        )
        existing_whitelist = await self._get_whitelisted_items(whitelist_type)
        if whitelist_item in existing_whitelist:
            await ctx.send(
                embed=Embed(
                    description=f"**{whitelist_item} already exists in the {whitelist_type} whitelist.**",
                    colour=Colour.red(),
                )
            )
        else:
            body = {"type": whitelist_type, "whitelisted_item": whitelist_item}
            await self.bot.api_client.post("bot/whitelist", json=body)

            log.debug(
                f"{ctx.author} successfully added the following items to our database: \n"
                f"whitelist_type: {whitelist_type}\n"
                f"whitelist_item: '{whitelist_item}'\n"
            )

            await ctx.send(
                embed=Embed(
                    title="Item successfully added",
                    description=f"**{whitelist_item}** added to {whitelist_type} whitelist database.",
                    colour=Colour.blurple(),
                )
            )

    @whitelist_group.command(name="get", aliases=("show", "g"))
    @with_role(Roles.owners, Roles.admins)
    async def get_command(self, ctx: Context, *, whitelist_type: str) -> None:
        """Get a list of whitelisted items under whitelist_type."""
        params = {"type": whitelist_type}
        res_json = await self.bot.api_client.get(f"bot/whitelist", params=params)
        whitelisted_items = [
            f'{item["whitelisted_item"]} (id: {item["id"]})' for item in res_json
        ]
        embed: Embed = Embed(
            title=f"**Current Whitelisted items under {whitelist_type}**"
        )
        await LinePaginator.paginate(
            [f"**{idx + 1}.** {item}" for idx, item in enumerate(whitelisted_items)],
            ctx,
            embed,
            empty=False,
            max_lines=15,
        )

    @whitelist_group.command(name="delete", aliases=("remove", "rm", "d"))
    @with_role(Roles.owners, Roles.admins)
    async def delete_command(self, ctx: Context, id_: int) -> None:
        """Remove Item from whitelist."""
        await self.bot.api_client.delete(f"bot/whitelist/{id_}")

        log.debug(
            f"{ctx.author} successfully removed the item with id {id_} from whitelist."
        )
        await ctx.send(
            embed=Embed(
                description=f"Item has been removed successfully!",
                colour=Colour.blurple(),
            )
        )


def setup(bot: Bot) -> None:
    """Whitelist cog load."""
    bot.add_cog(Whitelist(bot))
