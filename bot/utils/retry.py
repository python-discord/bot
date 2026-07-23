from pydis_core.site_api import ResponseCodeError


def is_retryable_api_error(error: Exception) -> bool:
    """Return whether an API error is temporary and worth retrying."""
    if isinstance(error, ResponseCodeError):
        return error.status in (408, 429) or error.status >= 500

    return isinstance(error, (TimeoutError, OSError))
