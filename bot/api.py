import asyncio
import logging
from typing import Optional
from urllib.parse import quote as quote_url

import aiohttp

from .constants import Keys, URLs

log = logging.getLogger(__name__)


class ResponseCodeError(ValueError):
    """Raised when a non-OK HTTP response is received."""

    def __init__(
        self,
        response: aiohttp.ClientResponse,
        response_json: Optional[dict] = None,
        response_text: str = ""
    ):
        self.status = response.status
        self.response_json = response_json or {}
        self.response_text = response_text
        self.response = response

    def __str__(self):
        response = self.response_json if self.response_json else self.response_text
        return f"Status: {self.status} Response: {response}"


class APIClient:
    """Django Site API wrapper."""

    # These are class attributes so they can be seen when being mocked for tests.
    # See commit 22a55534ef13990815a6f69d361e2a12693075d5 for details.
    session: Optional[aiohttp.ClientSession] = None
    loop: asyncio.AbstractEventLoop = None

    def __init__(self, loop: asyncio.AbstractEventLoop, **kwargs):
        auth_headers = {
            'Authorization': f"Token {Keys.site_api}"
        }

        if 'headers' in kwargs:
            kwargs['headers'].update(auth_headers)
        else:
            kwargs['headers'] = auth_headers

        self.session = None
        self.loop = loop

        self._ready = asyncio.Event(loop=loop)
        self._creation_task = None
        self._default_session_kwargs = kwargs

        self.recreate()

    @staticmethod
    def _url_for(endpoint: str) -> str:
        return f"{URLs.site_schema}{URLs.site_api}/{quote_url(endpoint)}"

    async def _create_session(self, **session_kwargs) -> None:
        """
        Create the aiohttp session with `session_kwargs` and set the ready event.

        `session_kwargs` is merged with `_default_session_kwargs` and overwrites its values.
        If an open session already exists, it will first be closed.
        """
        await self.close()
        self.session = aiohttp.ClientSession(**{**self._default_session_kwargs, **session_kwargs})
        self._ready.set()

    async def close(self) -> None:
        """Close the aiohttp session and unset the ready event."""
        if self.session:
            await self.session.close()

        self._ready.clear()

    def recreate(self, force: bool = False, **session_kwargs) -> None:
        """
        Schedule the aiohttp session to be created with `session_kwargs` if it's been closed.

        If `force` is True, the session will be recreated even if an open one exists. If a task to
        create the session is pending, it will be cancelled.

        `session_kwargs` is merged with the kwargs given when the `APIClient` was created and
        overwrites those default kwargs.
        """
        if force or self.session is None or self.session.closed:
            if force and self._creation_task:
                self._creation_task.cancel()

            # Don't schedule a task if one is already in progress.
            if force or self._creation_task is None or self._creation_task.done():
                self._creation_task = self.loop.create_task(self._create_session(**session_kwargs))

    async def maybe_raise_for_status(self, response: aiohttp.ClientResponse, should_raise: bool) -> None:
        """Raise ResponseCodeError for non-OK response if an exception should be raised."""
        if should_raise and response.status >= 400:
            try:
                response_json = await response.json()
                raise ResponseCodeError(response=response, response_json=response_json)
            except aiohttp.ContentTypeError:
                response_text = await response.text()
                raise ResponseCodeError(response=response, response_text=response_text)

    async def request(self, method: str, endpoint: str, *, raise_for_status: bool = True, **kwargs) -> dict:
        """Send an HTTP request to the site API and return the JSON response."""
        await self._ready.wait()

        async with self.session.request(method.upper(), self._url_for(endpoint), **kwargs) as resp:
            await self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def get(self, endpoint: str, *, raise_for_status: bool = True, **kwargs) -> dict:
        """Site API GET."""
        return await self.request("GET", endpoint, raise_for_status=raise_for_status, **kwargs)

    async def patch(self, endpoint: str, *, raise_for_status: bool = True, **kwargs) -> dict:
        """Site API PATCH."""
        return await self.request("PATCH", endpoint, raise_for_status=raise_for_status, **kwargs)

    async def post(self, endpoint: str, *, raise_for_status: bool = True, **kwargs) -> dict:
        """Site API POST."""
        return await self.request("POST", endpoint, raise_for_status=raise_for_status, **kwargs)

    async def put(self, endpoint: str, *, raise_for_status: bool = True, **kwargs) -> dict:
        """Site API PUT."""
        return await self.request("PUT", endpoint, raise_for_status=raise_for_status, **kwargs)

    async def delete(self, endpoint: str, *, raise_for_status: bool = True, **kwargs) -> Optional[dict]:
        """Site API DELETE."""
        await self._ready.wait()

        async with self.session.delete(self._url_for(endpoint), **kwargs) as resp:
            if resp.status == 204:
                return None

            await self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()


def loop_is_running() -> bool:
    """
    Determine if there is a running asyncio event loop.

    This helps enable "call this when event loop is running" logic (see: Twisted's `callWhenRunning`),
    which is currently not provided by asyncio.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True
