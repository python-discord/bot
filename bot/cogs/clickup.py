# coding=utf-8
from aiohttp import ClientSession

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import ADMIN_ROLE, CLICKUP_KEY, CLICKUP_SPACE, CLICKUP_TEAM, DEVOPS_ROLE, MODERATOR_ROLE, OWNER_ROLE
from bot.decorators import with_role

CREATE_TASK_URL = "https://api.clickup.com/api/v1/list/{list_id}/task"
GET_TASKS_URL = "https://api.clickup.com/api/v1/team/{team_id}/task"
PROJECTS_URL = "https://api.clickup.com/api/v1/space/{space_id}/project"

# Don't ask me why the below line is a syntax error, but that's what flake8 thinks...
SPACES_URL = "https://api.clickup.com/api/v1/team/{team_id}/space"  # flake8: noqa
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

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @command(name="clickup.tasks()", aliases=["clickup.tasks", "tasks"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def tasks(self, ctx: Context, task_list: int = None, status: str = None):
        """
        Get a list of tasks, optionally on a specific list or with a specific status
        """

        params = {}

        if task_list:
            params["list_ids"] = task_list

        if status:
            params["statuses"] = status

        with ClientSession() as session:
            response = await session.get(GET_TASKS_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS, params=params)
            result = await response.json()

        lines = []

        for task in result["tasks"]:
            # \u00BB is a right-pointing double chevron
            lines.append(
                f"{task['id']} \u00BB {task['name']}: {task['status']['status']}\n"
            )

        message = ""

        while lines:
            item = lines.pop(0)

            if len(message) + len(item) < 2000:
                message += item
            else:
                message += f"...and {len(lines)} more"
                break

        embed = Embed(description=message)

        embed.set_author(
            name="ClickUp Members",
            icon_url="https://clickup.com/landing/favicons/favicon-32x32.png",
            url=f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/"
        )

        await ctx.send(embed=embed)

    @command(name="clickup.team()", aliases=["clickup.team", "team"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def team(self, ctx: Context):
        """
        Get a list of every member of the team
        """

        with ClientSession() as session:
            response = await session.get(TEAM_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS)
            result = await response.json()

        embed = Embed(
            colour=Colour.blurple()
        )

        for member in result["team"]["members"]:
            embed.add_field(
                name=member["user"]["username"],
                value=member["user"]["id"]
            )

        embed.set_author(
            name="ClickUp Members",
            icon_url="https://clickup.com/landing/favicons/favicon-32x32.png",
            url=f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/"
        )

        await ctx.send(embed=embed)

    @command(name="clickup.lists()", aliases=["clickup.lists", "lists"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def lists(self, ctx: Context):
        """
        Get all the lists belonging to the ClickUp space
        """

        with ClientSession() as session:
            response = await session.get(PROJECTS_URL.format(space_id=CLICKUP_SPACE), headers=HEADERS)
            result = await response.json()

        embed = Embed(
            colour=Colour.blurple()
        )

        for project in result["projects"]:
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
            url=f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/"
        )

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(ClickUp(bot))
    print("Cog loaded: ClickUp")
