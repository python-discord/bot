import logging

from discord import Colour, Embed
from discord.ext.commands import Bot, Context, group

from bot.constants import URLs

log = logging.getLogger(__name__)

INFO_URL = f"{URLs.site_schema}{URLs.site}/info"


class Site:
    """Commands for linking to different parts of the site."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(name="site", aliases=("s",), invoke_without_command=True)
    async def site_group(self, ctx):
        """Commands for getting info about our website."""

        await ctx.invoke(self.bot.get_command("help"), "site")

    @site_group.command(name="home", aliases=("about",))
    async def site_main(self, ctx: Context):
        """Info about the website itself."""

        url = f"{URLs.site_schema}{URLs.site}/"

        embed = Embed(title="Python Discord website")
        embed.set_footer(text=url)
        embed.colour = Colour.blurple()
        embed.description = (
            f"[Our official website]({url}) is an open-source community project "
            "created with Python and Flask. It contains information about the server "
            "itself, lets you sign up for upcoming events, has its own wiki, contains "
            "a list of valuable learning resources, and much more."
        )

        await ctx.send(embed=embed)

    @site_group.command(name="resources")
    async def site_resources(self, ctx: Context):
        """Info about the site's Resources page."""

        url = f"{INFO_URL}/resources"

        embed = Embed(title="Resources")
        embed.set_footer(text=url)
        embed.colour = Colour.blurple()
        embed.description = (
            f"The [Resources page]({url}) on our website contains a "
            "list of hand-selected goodies that we regularly recommend "
            "to both beginners and experts."
        )

        await ctx.send(embed=embed)

    @site_group.command(name="help")
    async def site_help(self, ctx: Context):
        """Info about the site's Getting Help page."""

        url = f"{INFO_URL}/help"

        embed = Embed(title="Getting Help")
        embed.set_footer(text=url)
        embed.colour = Colour.blurple()
        embed.description = (
            "Asking the right question about something that's new to you can sometimes be tricky. "
            f"To help with this, we've created a [guide to asking good questions]({url}) on our website. "
            "It contains everything you need to get the very best help from our community."
        )

        await ctx.send(embed=embed)

    @site_group.command(name="faq")
    async def site_faq(self, ctx: Context):
        """Info about the site's FAQ page."""

        url = f"{INFO_URL}/faq"

        embed = Embed(title="FAQ")
        embed.set_footer(text=url)
        embed.colour = Colour.blurple()
        embed.description = (
            "As the largest Python community on Discord, we get hundreds of questions every day. "
            "Many of these questions have been asked before. We've compiled a list of the most "
            "frequently asked questions along with their answers, which can be found on "
            f"our [FAQ page]({url})."
        )

        await ctx.send(embed=embed)

    @site_group.command(name="rules")
    async def site_rules(self, ctx: Context):
        """Info about the server's rules."""

        url = f"{URLs.site_schema}{URLs.site}/about/rules"

        embed = Embed(title="Rules")
        embed.set_footer(text=url)
        embed.colour = Colour.blurple()
        embed.description = (
            f"The rules and guidelines that apply to this community can be found on our [rules page]({url}). "
            "We expect all members of the community to have read and understood these."
        )

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Site(bot))
    log.info("Cog loaded: Site")
