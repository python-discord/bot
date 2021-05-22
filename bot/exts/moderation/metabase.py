import csv
import json
import logging
from datetime import timedelta
from io import StringIO
from typing import Dict, List, Optional

import arrow
from aiohttp.client_exceptions import ClientResponseError
from arrow import Arrow
from async_rediscache import RedisCache
from discord.ext.commands import Cog, Context, group, has_any_role

from bot.bot import Bot
from bot.constants import Metabase as MetabaseConfig, Roles
from bot.converters import allowed_strings
from bot.utils import send_to_paste_service
from bot.utils.channel import is_mod_channel
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)

BASE_HEADERS = {
    "Content-Type": "application/json"
}


class Metabase(Cog):
    """Commands for admins to interact with metabase."""

    session_info = RedisCache()

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._session_scheduler = Scheduler(self.__class__.__name__)

        self.session_token: Optional[str] = None  # session_info["session_token"]: str
        self.session_expiry: Optional[float] = None  # session_info["session_expiry"]: UtcPosixTimestamp
        self.headers = BASE_HEADERS

        self.exports: Dict[int, List[Dict]] = {}  # Saves the output of each question, so internal eval can access it

        self.init_task = self.bot.loop.create_task(self.init_cog())

    async def init_cog(self) -> None:
        """Initialise the metabase session."""
        expiry_time = await self.session_info.get("session_expiry")
        if expiry_time:
            expiry_time = Arrow.utcfromtimestamp(expiry_time)

        if expiry_time is None or expiry_time < arrow.utcnow():
            # Force a refresh and end the task
            await self.refresh_session()
            return

        # Cached token is in date, so get it and schedule a refresh for later
        self.session_token = await self.session_info.get("session_token")
        self.headers["X-Metabase-Session"] = self.session_token

        self._session_scheduler.schedule_at(expiry_time, 0, self.refresh_session())

    async def refresh_session(self) -> None:
        """Refresh metabase session token."""
        data = {
            "username": MetabaseConfig.username,
            "password": MetabaseConfig.password
        }
        async with self.bot.http_session.post(f"{MetabaseConfig.url}/session", json=data) as resp:
            json_data = await resp.json()
            self.session_token = json_data.get("id")

        self.headers["X-Metabase-Session"] = self.session_token
        log.info("Successfully updated metabase session.")

        # When the creds are going to expire
        refresh_time = arrow.utcnow() + timedelta(minutes=MetabaseConfig.max_session_age)

        # Cache the session info, since login in heavily ratelimitted
        await self.session_info.set("session_token", self.session_token)
        await self.session_info.set("session_expiry", refresh_time.timestamp())

        self._session_scheduler.schedule_at(refresh_time, 0, self.refresh_session())

    @group(name="metabase", invoke_without_command=True)
    async def metabase_group(self, ctx: Context) -> None:
        """A group of commands for interacting with metabase."""
        await ctx.send_help(ctx.command)

    @metabase_group.command(name="extract")
    async def metabase_extract(
        self,
        ctx: Context,
        question_id: int,
        extension: allowed_strings("csv", "json") = "csv"
    ) -> None:
        """
        Extract data from a metabase question.

        You can find the question_id at the end of the url on metabase.
        I.E. /question/{question_id}

        If, instead of an id, there is a long URL, make sure to save the question first.

        If you want to extract data from a question within a dashboard, click the
        question title at the top left of the chart to go directly to that page.

        Valid extensions are: csv and json.
        """
        async with ctx.typing():

            # Make sure we have a session token before running anything
            await self.init_task

            url = f"{MetabaseConfig.url}/card/{question_id}/query/{extension}"
            try:
                async with self.bot.http_session.post(url, headers=self.headers, raise_for_status=True) as resp:
                    if extension == "csv":
                        out = await resp.text()
                        # Save the output for use with int e
                        self.exports[question_id] = list(csv.DictReader(StringIO(out)))

                    elif extension == "json":
                        out = await resp.json()
                        # Save the output for use with int e
                        self.exports[question_id] = out

                        # Format it nicely for human eyes
                        out = json.dumps(out, indent=4, sort_keys=True)
            except ClientResponseError as e:
                if e.status == 403:
                    # User doesn't have access to the given question
                    log.warning(f"Failed to auth with Metabase for question {question_id}.")
                    await ctx.send(f":x: {ctx.author.mention} Failed to auth with Metabase for that question.")
                else:
                    # User credentials are invalid, or the refresh failed.
                    # Delete the expiry time, to force a refresh on next startup.
                    await self.session_info.delete("session_expiry")
                    log.exception("Session token is invalid or refresh failed.")
                    await ctx.send(f":x: {ctx.author.mention} Session token is invalid or refresh failed.")
                return

            paste_link = await send_to_paste_service(out, extension=extension)
            if paste_link:
                message = f":+1: {ctx.author.mention} Here's your link: {paste_link}"
            else:
                message = f":x: {ctx.author.mention} Link service is unavailible."
            await ctx.send(
                f"{message}\nYou can also access this data within internal eval by doing: "
                f"`bot.get_cog('Metabase').exports[{question_id}]`"
            )

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allow admins inside moderator channels to invoke the commands in this cog."""
        checks = [
            await has_any_role(Roles.admins).predicate(ctx),
            is_mod_channel(ctx.channel)
        ]
        return all(checks)

    def cog_unload(self) -> None:
        """
        Cancel the init task and scheduled tasks.

        It's important to wait for init_task to be cancelled before cancelling scheduled
        tasks. Otherwise, it's possible for _session_scheduler to schedule another task
        after cancel_all has finished, despite _init_task.cancel being called first.
        This is cause cancel() on its own doesn't block until the task is cancelled.
        """
        self.init_task.cancel()
        self.init_task.add_done_callback(lambda _: self._session_scheduler.cancel_all())


def setup(bot: Bot) -> None:
    """Load the Metabase cog."""
    if not all((MetabaseConfig.username, MetabaseConfig.password)):
        log.error("Credentials not provided, cog not loaded.")
        return
    bot.add_cog(Metabase(bot))
