import logging

from discord import Colour, Embed
from discord.ext.commands import Cog, Context, Greedy, group

from bot.bot import Bot
from bot.constants import URLs
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)

PAGES_URL = f"{URLs.site_schema}{URLs.site}/pages"


class Site(Cog):
    """Commands for linking to different parts of the site."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(name="site", aliases=("s",), invoke_without_command=True)
    async def site_group(self, ctx: Context) -> None:
        """Commands for getting info about our website."""
        await ctx.send_help(ctx.command)

    @site_group.command(name="home", aliases=("about",), root_aliases=("home",))
    async def site_main(self, ctx: Context) -> None:
        """Info about the website itself."""
        url = f"{URLs.site_schema}{URLs.site}/"

        embed = Embed(title="Python Discord website")
        embed.set_footer(text=url)
        embed.colour = Colour.blurple()
        embed.description = (
            f"[Our official website]({url}) is an open-source community project "
            "created with Python and Django. It contains information about the server "
            "itself, lets you sign up for upcoming events, has its own wiki, contains "
            "a list of valuable learning resources, and much more."
        )

        await ctx.send(embed=embed)

    @site_group.command(name="resources", root_aliases=("resources", "resource"))
    async def site_resources(self, ctx: Context) -> None:
        """Info about the site's Resources page."""
        learning_url = f"{PAGES_URL}/resources"

        embed = Embed(title="Resources")
        embed.set_footer(text=f"{learning_url}")
        embed.colour = Colour.blurple()
        embed.description = (
            f"The [Resources page]({learning_url}) on our website contains a "
            "list of hand-selected learning resources that we regularly recommend "
            f"to both beginners and experts."
        )

        await ctx.send(embed=embed)

    @site_group.command(name="tools", root_aliases=("tools",))
    async def site_tools(self, ctx: Context) -> None:
        """Info about the site's Tools page."""
        tools_url = f"{PAGES_URL}/resources/tools"

        embed = Embed(title="Tools")
        embed.set_footer(text=f"{tools_url}")
        embed.colour = Colour.blurple()
        embed.description = (
            f"The [Tools page]({tools_url}) on our website contains a "
            f"couple of the most popular tools for programming in Python."
        )

        await ctx.send(embed=embed)

    @site_group.command(name="help")
    async def site_help(self, ctx: Context) -> None:
        """Info about the site's Getting Help page."""
        url = f"{PAGES_URL}/resources/guides/asking-good-questions"

        embed = Embed(title="Asking Good Questions")
        embed.set_footer(text=url)
        embed.colour = Colour.blurple()
        embed.description = (
            "Asking the right question about something that's new to you can sometimes be tricky. "
            f"To help with this, we've created a [guide to asking good questions]({url}) on our website. "
            "It contains everything you need to get the very best help from our community."
        )

        await ctx.send(embed=embed)

    @site_group.command(name="faq", root_aliases=("faq",))
    async def site_faq(self, ctx: Context) -> None:
        """Info about the site's FAQ page."""
        url = f"{PAGES_URL}/frequently-asked-questions"

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

    @site_group.command(name="rules", aliases=("r", "rule"), root_aliases=("rules", "rule"))
    async def site_rules(self, ctx: Context, rules: Greedy[int]) -> None:
        """Provides a link to all rules or, if specified, displays specific rule(s)."""
        rules_embed = Embed(title='Rules', color=Colour.blurple(), url=f'{PAGES_URL}/rules')

        if not rules:
            # Rules were not submitted. Return the default description.
            rules_embed.description = (
                "The rules and guidelines that apply to this community can be found on"
                f" our [rules page]({PAGES_URL}/rules). We expect"
                " all members of the community to have read and understood these."
            )

            await ctx.send(embed=rules_embed)
            return

        full_rules = await self.bot.api_client.get('rules', params={'link_format': 'md'})

        # Remove duplicates and sort the rule indices
        rules = sorted(set(rules))
        invalid = ', '.join(str(index) for index in rules if index < 1 or index > len(full_rules))

        if invalid:
            await ctx.send(f":x: Invalid rule indices: {invalid}")
            return

        for rule in rules:
            self.bot.stats.incr(f"rule_uses.{rule}")

        final_rules = tuple(f"**{pick}.** {full_rules[pick - 1]}" for pick in rules)

        await LinePaginator.paginate(final_rules, ctx, rules_embed, max_lines=3)


def setup(bot: Bot) -> None:
    """Load the Site cog."""
    bot.add_cog(Site(bot))
