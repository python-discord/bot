from urllib.parse import quote as quote_url

import aiohttp

from .constants import Keys, URLs


class ResponseCodeError(ValueError):
    def __init__(self, response: aiohttp.ClientResponse):
        self.response = response


class APIClient:
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
    def _url_for(endpoint: str):
        return f"{URLs.site_schema}{URLs.site_api}/{quote_url(endpoint)}"

    def maybe_raise_for_status(self, response: aiohttp.ClientResponse, should_raise: bool):
        if should_raise and response.status >= 400:
            raise ResponseCodeError(response=response)

    async def get(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs):
        async with self.session.get(self._url_for(endpoint), *args, **kwargs) as resp:
            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def patch(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs):
        async with self.session.patch(self._url_for(endpoint), *args, **kwargs) as resp:
            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def post(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs):
        async with self.session.post(self._url_for(endpoint), *args, **kwargs) as resp:
            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def put(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs):
        async with self.session.put(self._url_for(endpoint), *args, **kwargs) as resp:
            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()

    async def delete(self, endpoint: str, *args, raise_for_status: bool = True, **kwargs):
        async with self.session.delete(self._url_for(endpoint), *args, **kwargs) as resp:
            if resp.status == 204:
                return None

            self.maybe_raise_for_status(resp, raise_for_status)
            return await resp.json()
