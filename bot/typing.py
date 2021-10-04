import logging
from datetime import datetime, timedelta

from discord import Forbidden, http

log = logging.getLogger(__name__)


def patch_typing() -> None:
    """
    Sometimes discord turns off typing events by throwing 403's.

    Handle those issues by patching the trigger_typing method so it ignores 403's in general.
    """
    log.info("Patching send_typing, which should fix things breaking when discord disables typing events. Stay safe!")

    original = http.HTTPClient.send_typing
    last_403 = None

    async def honeybadger_type(self, channel_id: int) -> None:  # noqa: ANN001
        nonlocal last_403
        if last_403 and (datetime.now() - last_403) < timedelta(minutes=5):
            log.warning("Not sending typing event, we got a 403 less than 5 minutes ago.")
            return
        try:
            await original(self, channel_id)
        except Forbidden:
            last_403 = datetime.now()
            log.warning("Got a 403 from typing event!")
            pass

    http.HTTPClient.send_typing = honeybadger_type
