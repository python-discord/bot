from unittest.mock import MagicMock


__all__ = ('AsyncMock',)


# TODO: Remove me on 3.8
class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)
