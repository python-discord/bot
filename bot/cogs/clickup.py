# coding=utf-8
from aiohttp import ClientSession

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import ADMIN_ROLE, CLICKUP_KEY, CLICKUP_SPACE, CLICKUP_TEAM, DEVOPS_ROLE, MODERATOR_ROLE, OWNER_ROLE
from bot.decorators import with_role

CREATE_TASK_URL = "https://api.clickup.com/api/v1/list/{list_id}/task"
PROJECTS_URL = "https://api.clickup.com/api/v1/space/{space_id}/project"
SPACES_URL = "https://api.clickup.com/api/v1/team/{team_id}/space"
TEAM_URL = "https://api.clickup.com/api/v1/team/{team_id}"

HEADERS = {
    "Authorization": CLICKUP_KEY,
    "Content-Type": "application/json"
}


class ClickUp:
    """
    ClickUp management commands
    """

    # Set statuses: Open, In Progress, Review, Closed
    # Open task
    # Assign task
    # Get tasks
    # Get user IDs
    # Get lists

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.space_id = 0

    async def on_ready(self):
        with ClientSession() as session:
            response = await session.get(SPACES_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS)
            result = response.json()

        self.space_id = result[0]["id"]

    @command(name="clickup.lists()", aliases=["clickup.lists", "lists"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def lists(self, ctx: Context):
        """
        Get all the lists belonging to the ClickUp space
        """

        with ClientSession() as session:
            response = await session.get(PROJECTS_URL.format(space_id=CLICKUP_SPACE), headers=HEADERS)
            result = response.json()

        embed = Embed(
            colour=Colour.blurple()
        )

        for project in result:
            lists = []

            for list_ in project["lists"]:
                lists.append(f"{list_['name']} ({list_['id']})")

            lists = "\n".join(lists)

            embed.add_field(
                name=f"{project['name']} ({project['id']})",
                value=lists
            )

        embed.set_author(
            name="ClickUp Projects",
            icon_url="https://clickup.com/landing/favicons/favicon-32x32.png",
            url="https://app.clickup.com/754996/757069/"
        )

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(ClickUp(bot))
    print("Cog loaded: ClickUp")
