# coding=utf-8
import logging

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from multidict import MultiDict

from bot.constants import (
    ADMIN_ROLE, CLICKUP_KEY, CLICKUP_SPACE, CLICKUP_TEAM, DEVOPS_ROLE, MODERATOR_ROLE, OWNER_ROLE
)
from bot.decorators import with_role
from bot.pagination import LinePaginator
from bot.utils import CaseInsensitiveDict

CREATE_TASK_URL = "https://api.clickup.com/api/v1/list/{list_id}/task"
EDIT_TASK_URL = "https://api.clickup.com/api/v1/task/{task_id}"
GET_TASKS_URL = "https://api.clickup.com/api/v1/team/{team_id}/task"
PROJECTS_URL = "https://api.clickup.com/api/v1/space/{space_id}/project"
SPACES_URL = "https://api.clickup.com/api/v1/team/{team_id}/space"
TEAM_URL = "https://api.clickup.com/api/v1/team/{team_id}"

HEADERS = {
    "Authorization": CLICKUP_KEY,
    "Content-Type": "application/json"
}

STATUSES = ["open", "in progress", "review", "closed"]

log = logging.getLogger(__name__)


class ClickUp:
    """
    ClickUp management commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.lists = CaseInsensitiveDict()

    async def on_ready(self):
        response = await self.bot.http_session.get(
            PROJECTS_URL.format(space_id=CLICKUP_SPACE), headers=HEADERS
        )
        result = await response.json()

        if "err" in result:
            log.error(f"Failed to get ClickUp lists: `{result['ECODE']}`: {result['err']}")
        else:
            # Save all the lists with their IDs so that we can get at them later
            for project in result["projects"]:
                for list_ in project["lists"]:
                    self.lists[list_["name"]] = list_["id"]
                    self.lists[f"{project['name']}/{list_['name']}"] = list_["id"]  # Just in case we have duplicates

            # Add the reverse so we can look up by ID as well
            self.lists.update({v: k for k, v in self.lists.items()})

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
                log.warning(f"{ctx.author} requested '{task_list}', but that list is unknown. Rejecting request.")
                embed.description = f"Unknown list: {task_list}"
                embed.colour = Colour.red()
                return await ctx.send(embed=embed)

        if status and status != "*":
            params["statuses[]"] = status

        response = await self.bot.http_session.get(
            GET_TASKS_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS, params=params
        )
        result = await response.json()

        if "err" in result:
            log.error("ClickUp responded to the task list request with an error!\n"
                      f"error code: '{result['ECODE']}'\n"
                      f"error: {result['err']}")
            embed.description = f"`{result['ECODE']}`: {result['err']}"
            embed.colour = Colour.red()

        else:
            tasks = result["tasks"]

            if not tasks:
                log.debug("{ctx.author} requested a list of ClickUp tasks, but no ClickUp tasks were found.")
                embed.description = "No tasks found."
                embed.colour = Colour.red()

            else:
                lines = []

                for task in tasks:
                    task_url = f"http://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/t/{task['id']}"
                    id_fragment = f"[`#{task['id']: <5}`]({task_url})"
                    status = f"{task['status']['status'].title()}"

                    lines.append(f"{id_fragment} ({status})\n\u00BB {task['name']}")

                log.debug(f"{ctx.author} requested a list of ClickUp tasks. Returning list.")
                return await LinePaginator.paginate(lines, ctx, embed, max_size=750)
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

        response = await self.bot.http_session.get(
            GET_TASKS_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS, params=params
        )
        result = await response.json()

        if "err" in result:
            log.error("ClickUp responded to the get task request with an error!\n"
                      f"error code: '{result['ECODE']}'\n"
                      f"error: {result['err']}")
            embed.description = f"`{result['ECODE']}`: {result['err']}"
            embed.colour = Colour.red()
        else:
            task = None

            for task_ in result["tasks"]:
                if task_["id"] == task_id:
                    task = task_
                    break

            if task is None:
                log.warning(f"{ctx.author} requested the task '#{task_id}', but it could not be found.")
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

                log.debug(f"{ctx.author} requested the task '#{task_id}'. Returning the task data.")
                return await LinePaginator.paginate(lines, ctx, embed, max_size=750)
        return await ctx.send(embed=embed)

    @command(name="clickup.team()", aliases=["clickup.team", "team", "list_team"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def team_command(self, ctx: Context):
        """
        Get a list of every member of the team
        """

        response = await self.bot.http_session.get(
            TEAM_URL.format(team_id=CLICKUP_TEAM), headers=HEADERS
        )
        result = await response.json()

        if "err" in result:
            log.error("ClickUp responded to the team request with an error!\n"
                      f"error code: '{result['ECODE']}'\n"
                      f"error: {result['err']}")
            embed = Embed(
                colour=Colour.red(),
                description=f"`{result['ECODE']}`: {result['err']}"
            )
        else:
            log.debug(f"{ctx.author} requested a list of team members. Preparing the list...")
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

        log.debug("List fully prepared, returning list to channel.")
        await ctx.send(embed=embed)

    @command(name="clickup.lists()", aliases=["clickup.lists", "lists"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def lists_command(self, ctx: Context):
        """
        Get all the lists belonging to the ClickUp space
        """

        response = await self.bot.http_session.get(
            PROJECTS_URL.format(space_id=CLICKUP_SPACE), headers=HEADERS
        )
        result = await response.json()

        if "err" in result:
            log.error("ClickUp responded to the lists request with an error!\n"
                      f"error code: '{result['ECODE']}'\n"
                      f"error: {result['err']}")
            embed = Embed(
                colour=Colour.red(),
                description=f"`{result['ECODE']}`: {result['err']}"
            )
        else:
            log.debug(f"{ctx.author} requested a list of all ClickUp lists. Preparing the list...")
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

        log.debug(f"List fully prepared, returning list to channel.")
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
            log.warning(f"{ctx.author} tried to open a new task on ClickUp, "
                        f"but '{task_list}' is not a known list. Rejecting request.")
            embed.description = f"Unknown list: {task_list}"
            embed.colour = Colour.red()
            return await ctx.send(embed=embed)

        response = await self.bot.http_session.post(
            CREATE_TASK_URL.format(list_id=task_list), headers=HEADERS, json={
                "name": title,
                "status": "Open"
            }
        )
        result = await response.json()

        if "err" in result:
            log.error("ClickUp responded to the get task request with an error!\n"
                      f"error code: '{result['ECODE']}'\n"
                      f"error: {result['err']}")
            embed.colour = Colour.red()
            embed.description = f"`{result['ECODE']}`: {result['err']}"
        else:
            task_id = result.get("id")
            task_url = f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/t/{task_id}"
            project, task_list = self.lists[task_list].split("/", 1)
            task_list = f"{project.title()}/{task_list.title()}"

            log.debug(f"{ctx.author} opened a new task on ClickUp: \n"
                      f"{task_list} - #{task_id}")
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
            log.warning(f"{ctx.author} tried to update a task on ClickUp, but '{status}' is not a known status.")
            embed.description = f"Unknown status: {status}"
            embed.colour = Colour.red()
        else:
            response = await self.bot.http_session.put(
                EDIT_TASK_URL.format(task_id=task_id), headers=HEADERS, json={"status": status}
            )
            result = await response.json()

            if "err" in result:
                log.error("ClickUp responded to the get task request with an error!\n"
                          f"error code: '{result['ECODE']}'\n"
                          f"error: {result['err']}")
                embed.description = f"`{result['ECODE']}`: {result['err']}"
                embed.colour = Colour.red()
            else:
                log.debug(f"{ctx.author} updated a task on ClickUp: #{task_id}")
                task_url = f"https://app.clickup.com/{CLICKUP_TEAM}/{CLICKUP_SPACE}/t/{task_id}"
                embed.description = f"Task updated: [`#{task_id}`]({task_url})"

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(ClickUp(bot))
    log.info("Cog loaded: ClickUp")
