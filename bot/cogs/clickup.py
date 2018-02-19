# coding=utf-8
from aiohttp import ClientSession

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import (
    ADMIN_ROLE, CLICKUP_KEY, CLICKUP_SPACE, CLICKUP_TEAM, DEVOPS_ROLE, MODERATOR_ROLE, OWNER_ROLE
)
from bot.decorators import with_role
from bot.utils import CaseInsensitiveDict, paginate

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

LEFT_EMOJI = "\u2B05"
RIGHT_EMOJI = "\u27A1"

PAGE_EMOJI = [LEFT_EMOJI, RIGHT_EMOJI]


class ClickUp:
    """
    ClickUp management commands
    """

    # Set statuses: Open, In Progress, Review, Closed
    # Open task
    # Assign task

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.lists = CaseInsensitiveDict()

    async def on_ready(self):
        with ClientSession() as session:
            response = await session.get(PROJECTS_URL.format(space_id=CLICKUP_SPACE), headers=HEADERS)
            result = await response.json()

        if "err" in result:
            print(f"Failed to get ClickUp lists: `{result['ECODE']}`: {result['err']}")
        else:
            # Save all the lists with their IDs so that we can get at them later
            for project in result["projects"]:
                for list_ in project["lists"]:
                    self.lists[list_["name"]] = list_["id"]
                    self.lists[f"{project['name']}/{list_['name']}"] = list_["id"]  # Just in case we have duplicates

    @command(name="clickup.tasks()", aliases=["clickup.tasks", "tasks"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def tasks(self, ctx: Context, status: str = None, task_list: str = None):
        """
        Get a list of tasks, optionally on a specific list or with a specific status

        Provide "*" for the status to match everything except for "Closed".
        """

        params = {}

        embed = Embed(colour=Colour.blurple())
        embed.set_author(
            name="ClickUp Tasks",
            icon_url="https://clickup.com/landing/favicons/favicon-32x32.png",
            url=f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/"
        )

        if task_list:
            if task_list in self.lists:
                params["list_ids[]"] = self.lists[task_list]
            else:
                embed.colour = Colour.red()
                embed.description = f"Unknown list: {task_list}"
                return await ctx.send(embed=embed)

        if status and status != "*":
            params["statuses[]"] = status

        with ClientSession() as session:
            response = await session.get(GET_TASKS_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS, params=params)
            result = await response.json()

        if "err" in result:
            embed.description = f"`{result['ECODE']}`: {result['err']}"
            embed.colour = Colour.red()

        else:
            tasks = result["tasks"]

            if not tasks:
                embed.description = "No tasks found."
                embed.colour = Colour.red()
            else:
                return await paginate(
                    (
                        f"`#{task['id']: <5}` ({task['status']['status'].title()})\n\u00BB {task['name']}"
                        for task in tasks
                    ),
                    ctx, embed
                )
        return await ctx.send(embed=embed)

    @command(name="clickup.team()", aliases=["clickup.team", "team"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def team(self, ctx: Context):
        """
        Get a list of every member of the team
        """

        with ClientSession() as session:
            response = await session.get(TEAM_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS)
            result = await response.json()

        if "err" in result:
            embed = Embed(description=f"`{result['ECODE']}`: {result['err']}")
            embed.colour = Colour.red()
        else:
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

        if "err" in result:
            embed = Embed(description=f"`{result['ECODE']}`: {result['err']}")
            embed.colour = Colour.red()
        else:
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
