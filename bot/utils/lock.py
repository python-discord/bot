class LockGuard:
    """
    A context manager which acquires and releases a lock (mutex).

    Raise RuntimeError if trying to acquire a locked lock.
    """

    def __init__(self):
        self._locked = False

    def locked(self) -> bool:
        """Return True if currently locked or False if unlocked."""
        return self._locked

    def __enter__(self):
        if self._locked:
            raise RuntimeError("Cannot acquire a locked lock.")

        self._locked = True

    def __exit__(self, _exc_type, _exc_value, _traceback):  # noqa: ANN001
        self._locked = False
        return False  # Indicate any raised exception shouldn't be suppressed.
