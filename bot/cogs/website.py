import logging

from discord import Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import FREEWARE_ICON, FREE_ICON, PAID_ICON, SITE_PROTOCOL, SITE_URL
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)

PAYMENT_ICONS = {
    "paid": PAID_ICON,
    "optional": FREEWARE_ICON,
    "free": FREE_ICON
}


class Website:
    """
    Website-related commands
    """
    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @command(name="resources", aliases=["resources()"])
    async def resources_command(self, ctx: Context):
        """Send a paginated list of our resources page from the website"""
        resources_url = f"{SITE_PROTOCOL}://{SITE_URL}/static/resources.json"
        response = await self.bot.http_session.get(resources_url)
        page = await response.json()

        lines = []
        for heading, content in page.items():
            lines.append(f"__**{heading}**__")

            section_description = content["description"]
            lines.append(f"*{section_description}*")

            resources = content["resources"]
            for name, details in resources.items():
                url = details["url"]
                payment = details["payment"]
                item_description = details["description"]
                icon = PAYMENT_ICONS[payment]

                lines.append(f"{icon} **[{name}]({url})**")
                lines.append(f"{item_description}")

        embed = Embed()
        embed.title = "Useful Resources."
        embed.url = resources_url

        log.debug(f"{ctx.author} requested the resources list. Returning a paginated list.")
        await LinePaginator.paginate(lines, ctx, embed, max_size=1000)


def setup(bot):
    bot.add_cog(Website(bot))
    log.info("Cog loaded: Website")
