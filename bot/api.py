import asyncio
import logging
from typing import Union
from urllib.parse import quote as quote_url

import aiohttp

from .constants import Keys, URLs

log = logging.getLogger(__name__)


class ResponseCodeError(ValueError):
    """Represent a not-OK response code."""

    def __init__(self, response: aiohttp.ClientResponse):
        self.response = response


class APIClient:
    """Django Site API wrapper."""

    def __init__(self, **kwargs):
        auth_headers = {
            'Authorization': f"Token {Keys.site_api}"
        }

        if 'headers' in kwargs:
            kwargs['headers'].update(auth_headers)
        else:
            kwargs['headers'] = auth_headers

        self.session = aiohttp.ClientSession(**kwargs)

    @staticmethod
    def _url_for(endpoint: str) -> str:
        return f"{URLs.site_schema}{URLs.site_api}/{quote_url(endpoint)}"

    def maybe_raise_for_status(self, response: aiohttp.ClientResponse, should_raise: bool) -> None:
        """Raise ResponseCodeError for non-OK response if an exception should be raised."""
        if should_raise and response.status >= 400:
            raise ResponseCodeError(response=response)

    async def get(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs) -> dict:
        """Site API GET."""
        async with self.session.get(self._url_for(endpoint), *args, **kwargs) as resp:
            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def patch(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs) -> dict:
        """Site API PATCH."""
        async with self.session.patch(self._url_for(endpoint), *args, **kwargs) as resp:
            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def post(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs) -> dict:
        """Site API POST."""
        async with self.session.post(self._url_for(endpoint), *args, **kwargs) as resp:
            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def put(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs) -> dict:
        """Site API PUT."""
        async with self.session.put(self._url_for(endpoint), *args, **kwargs) as resp:
            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def delete(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs) -> Union[dict, None]:
        """Site API DELETE."""
        async with self.session.delete(self._url_for(endpoint), *args, **kwargs) as resp:
            if resp.status == 204:
                return None

            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()


def loop_is_running() -> bool:
    """
    Determine if there is a running asyncio event loop.

    This helps enable "call this when event loop is running" logic (see: Twisted's `callWhenRunning`),
    which is currently not provided by asyncio
    """
    # asyncio does not have a way to say "call this when the event
    # loop is running", see e.g. `callWhenRunning` from twisted.

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class APILoggingHandler(logging.StreamHandler):
    """Site API logging handler."""

    def __init__(self, client: APIClient):
        logging.StreamHandler.__init__(self)
        self.client = client

        # internal batch of shipoff tasks that must not be scheduled
        # on the event loop yet - scheduled when the event loop is ready.
        self.queue = []

    async def ship_off(self, payload: dict) -> None:
        """Ship log payload to the logging API."""
        try:
            await self.client.post('logs', json=payload)
        except ResponseCodeError as err:
            log.warning(
                "Cannot send logging record to the site, got code %d.",
                err.response.status,
                extra={'via_handler': True}
            )
        except Exception as err:
            log.warning(
                "Cannot send logging record to the site: %r",
                err,
                extra={'via_handler': True}
            )

    def emit(self, record: logging.LogRecord) -> None:
        """
        Determine if a log record should be shipped to the logging API.

        The following two conditions are set:
            1. Do not log anything below DEBUG
            2. Ignore log records from the logging handler
        """
        # Two checks are performed here:
        if (
                # 1. Do not log anything below `DEBUG`. This is only applicable
                #    for the monkeypatched `TRACE` logging level, which has a
                #    lower numeric value than `DEBUG`.
                record.levelno > logging.DEBUG
                # 2. Ignore logging messages which are sent by this logging
                #    handler itself. This is required because if we were to
                #    not ignore messages emitted by this handler, we would
                #    infinitely recurse back down into this logging handler,
                #    making the reactor run like crazy, and eventually OOM
                #    something. Let's not do that...
                and not record.__dict__.get('via_handler')
        ):
            payload = {
                'application': 'bot',
                'logger_name': record.name,
                'level': record.levelname.lower(),
                'module': record.module,
                'line': record.lineno,
                'message': self.format(record)
            }

            task = self.ship_off(payload)
            if not loop_is_running():
                self.queue.append(task)
            else:
                asyncio.create_task(task)
                self.schedule_queued_tasks()

    def schedule_queued_tasks(self) -> None:
        """Logging task scheduler."""
        for task in self.queue:
            asyncio.create_task(task)

        if self.queue:
            log.debug(
                "Scheduled %d pending logging tasks.",
                len(self.queue),
                extra={'via_handler': True}
            )

        self.queue.clear()
