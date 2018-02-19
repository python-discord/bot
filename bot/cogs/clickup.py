# coding=utf-8
from aiohttp import ClientSession

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from multidict import MultiDict

from bot.constants import (
    ADMIN_ROLE, CLICKUP_KEY, CLICKUP_SPACE, CLICKUP_TEAM, DEVOPS_ROLE, MODERATOR_ROLE, OWNER_ROLE
)
from bot.decorators import with_role
from bot.utils import CaseInsensitiveDict, paginate

CREATE_TASK_URL = "https://api.clickup.com/api/v1/list/{list_id}/task"
EDIT_TASK_URL = "https://api.clickup.com/api/v1/task/{task_id}"
GET_TASKS_URL = "https://api.clickup.com/api/v1/team/{team_id}/task"
PROJECTS_URL = "https://api.clickup.com/api/v1/space/{space_id}/project"

# Don't ask me why the below line is a syntax error, but that's what flake8 thinks...
SPACES_URL = "https://api.clickup.com/api/v1/team/{team_id}/space"  # flake8: noqa
TEAM_URL = "https://api.clickup.com/api/v1/team/{team_id}"

HEADERS = {
    "Authorization": CLICKUP_KEY,
    "Content-Type": "application/json"
}

STATUSES = ["open", "in progress", "review", "closed"]


class ClickUp:
    """
    ClickUp management commands
    """

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

            self.lists.update({v: k for k, v in self.lists.items()})  # Add the reverse so we can look up by ID as well

    @command(name="clickup.tasks()", aliases=["clickup.tasks", "tasks", "list_tasks"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def tasks_command(self, ctx: Context, status: str = None, task_list: str = None):
        """
        Get a list of tasks, optionally on a specific list or with a specific status

        Provide "*" for the status to match everything except for "Closed".

        When specifying a list you may use the list name on its own, but it is preferable to give the project name
        as well - for example, "Bot/Cogs". This is case-insensitive.
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
                embed.colour = Colour.red()
                embed.description = "No tasks found."
            else:
                lines = []

                for task in tasks:
                    task_url = f"http://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/t/{task['id']}"
                    id_fragment = f"[`#{task['id']: <5}`]({task_url})"
                    status = f"{task['status']['status'].title()}"

                    lines.append(f"{id_fragment} ({status})\n\u00BB {task['name']}")
                return await paginate(lines, ctx, embed, max_size=750)
        return await ctx.send(embed=embed)

    @command(name="clickup.task()", aliases=["clickup.task", "task", "get_task"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def task_command(self, ctx: Context, task_id: str):
        """
        Get a task and return information specific to it
        """

        embed = Embed(colour=Colour.blurple())
        embed.set_author(
            name=f"ClickUp Task: #{task_id}",
            icon_url="https://clickup.com/landing/favicons/favicon-32x32.png",
            url=f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/t/{task_id}"
        )

        params = MultiDict()
        params.add("statuses[]", "Open")
        params.add("statuses[]", "in progress")
        params.add("statuses[]", "review")
        params.add("statuses[]", "Closed")

        with ClientSession() as session:
            response = await session.get(GET_TASKS_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS, params=params)
            result = await response.json()

        if "err" in result:
            embed.description = f"`{result['ECODE']}`: {result['err']}"
            embed.colour = Colour.red()
        else:
            task = None

            for task_ in result["tasks"]:
                if task_["id"] == task_id:
                    task = task_
                    break

            if task is None:
                embed.description = f"Unable to find task with ID `#{task_id}`:"
                embed.colour = Colour.red()
            else:
                status = task['status']['status'].title()
                project, list_ = self.lists[task['list']['id']].split("/", 1)
                list_ = f"{project.title()}/{list_.title()}"
                first_line = f"**{list_}** \u00BB *{task['name']}* \n**Status**: {status}"

                if task.get("tags"):
                    tags = ", ".join(tag["name"].title() for tag in task["tags"])
                    first_line += f" / **Tags**: {tags}"

                lines = [first_line]

                if task.get("text_content"):
                    lines.append(task["text_content"])

                if task.get("assignees"):
                    assignees = ", ".join(user["username"] for user in task["assignees"])
                    lines.append(
                        f"**Assignees**\n{assignees}"
                    )

                return await paginate(lines, ctx, embed, max_size=750)
        return await ctx.send(embed=embed)

    @command(name="clickup.team()", aliases=["clickup.team", "team", "list_team"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def team_command(self, ctx: Context):
        """
        Get a list of every member of the team
        """

        with ClientSession() as session:
            response = await session.get(TEAM_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS)
            result = await response.json()

        if "err" in result:
            embed = Embed(
                colour=Colour.red(),
                description=f"`{result['ECODE']}`: {result['err']}"
            )
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
    async def lists_command(self, ctx: Context):
        """
        Get all the lists belonging to the ClickUp space
        """

        with ClientSession() as session:
            response = await session.get(PROJECTS_URL.format(space_id=CLICKUP_SPACE), headers=HEADERS)
            result = await response.json()

        if "err" in result:
            embed = Embed(
                colour=Colour.red(),
                description=f"`{result['ECODE']}`: {result['err']}"
            )
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

    @command(name="clickup.open()", aliases=["clickup.open", "open", "open_task"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def open_command(self, ctx: Context, task_list: str, *, title: str):
        """
        Open a new task under a specific task list, with a title

        When specifying a list you may use the list name on its own, but it is preferable to give the project name
        as well - for example, "Bot/Cogs". This is case-insensitive.
        """

        embed = Embed(colour=Colour.blurple())
        embed.set_author(
            name="ClickUp Tasks",
            icon_url="https://clickup.com/landing/favicons/favicon-32x32.png",
            url=f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/"
        )

        if task_list in self.lists:
            task_list = self.lists[task_list]
        else:
            embed.colour = Colour.red()
            embed.description = f"Unknown list: {task_list}"
            return await ctx.send(embed=embed)

        with ClientSession() as session:
            response = await session.post(
                CREATE_TASK_URL.format(list_id=task_list), headers=HEADERS, json={
                    "name": title,
                    "status": "Open"
                }
            )
            result = await response.json()

        if "err" in result:
            embed.colour = Colour.red()
            embed.description = f"`{result['ECODE']}`: {result['err']}"
        else:
            task_id = result.get("id")
            task_url = f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/t/{task_id}"
            project, task_list = self.lists[task_list].split("/", 1)
            task_list = f"{project.title()}/{task_list.title()}"

            embed.description = f"New task created: [{task_list} \u00BB `#{task_id}`]({task_url})"

        await ctx.send(embed=embed)

    @command(name="clickup.set_status()", aliases=["clickup.set_status", "set_status", "set_task_status"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def set_status_command(self, ctx: Context, task_id: str, *, status: str):
        """
        Update the status of a specific task
        """

        embed = Embed(colour=Colour.blurple())
        embed.set_author(
            name="ClickUp Tasks",
            icon_url="https://clickup.com/landing/favicons/favicon-32x32.png",
            url=f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/"
        )

        if status.lower() not in STATUSES:
            embed.colour = Colour.red()
            embed.description = f"Unknown status: {status}"
        else:
            with ClientSession() as session:
                response = await session.put(
                    EDIT_TASK_URL.format(task_id=task_id), headers=HEADERS, json={"status": status}
                )
                result = await response.json()

            if "err" in result:
                embed.description = f"`{result['ECODE']}`: {result['err']}"
                embed.colour = Colour.red()
            else:
                task_url = f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/t/{task_id}"
                embed.description = f"Task updated: [`#{task_id}`]({task_url})"

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(ClickUp(bot))
    print("Cog loaded: ClickUp")
