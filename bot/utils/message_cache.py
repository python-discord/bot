import typing as t
from math import ceil

from discord import Message


class MessageCache:
    """
    A data structure for caching messages.

    The cache is implemented as a circular buffer to allow constant time append, prepend, pop from either side,
    and lookup by index. The cache therefore does not support removal at an arbitrary index (although it can be
    implemented to work in linear time relative to the maximum size).

    The object additionally holds a mapping from Discord message ID's to the index in which the corresponding message
    is stored, to allow for constant time lookup by message ID.

    The cache has a size limit operating the same as with a collections.deque, and most of its method names mirror those
    of a deque.

    The implementation is transparent to the user: to the user the first element is always at index 0, and there are
    only as many elements as were inserted (meaning, without any pre-allocated placeholder values).
    """

    def __init__(self, maxlen: int, *, newest_first: bool = False):
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self.maxlen = maxlen
        self.newest_first = newest_first

        self._start = 0
        self._end = 0

        self._messages: list[Message | None] = [None] * self.maxlen
        self._message_id_mapping = {}
        self._message_metadata = {}

    def append(self, message: Message, *, metadata: dict | None = None) -> None:
        """Add the received message to the cache, depending on the order of messages defined by `newest_first`."""
        if self.newest_first:
            self._appendleft(message)
        else:
            self._appendright(message)
        self._message_metadata[message.id] = metadata

    def _appendright(self, message: Message) -> None:
        """Add the received message to the end of the cache."""
        if self._is_full():
            del self._message_id_mapping[self._messages[self._start].id]
            del self._message_metadata[self._messages[self._start].id]
            self._start = (self._start + 1) % self.maxlen

        self._messages[self._end] = message
        self._message_id_mapping[message.id] = self._end
        self._end = (self._end + 1) % self.maxlen

    def _appendleft(self, message: Message) -> None:
        """Add the received message to the beginning of the cache."""
        if self._is_full():
            self._end = (self._end - 1) % self.maxlen
            del self._message_id_mapping[self._messages[self._end].id]
            del self._message_metadata[self._messages[self._end].id]

        self._start = (self._start - 1) % self.maxlen
        self._messages[self._start] = message
        self._message_id_mapping[message.id] = self._start

    def pop(self) -> Message:
        """Remove the last message in the cache and return it."""
        if self._is_empty():
            raise IndexError("pop from an empty cache")

        self._end = (self._end - 1) % self.maxlen
        message = self._messages[self._end]
        del self._message_id_mapping[message.id]
        del self._message_metadata[message.id]
        self._messages[self._end] = None

        return message

    def popleft(self) -> Message:
        """Return the first message in the cache and return it."""
        if self._is_empty():
            raise IndexError("pop from an empty cache")

        message = self._messages[self._start]
        del self._message_id_mapping[message.id]
        del self._message_metadata[message.id]
        self._messages[self._start] = None
        self._start = (self._start + 1) % self.maxlen

        return message

    def clear(self) -> None:
        """Remove all messages from the cache."""
        self._messages = [None] * self.maxlen
        self._message_id_mapping = {}
        self._message_metadata = {}

        self._start = 0
        self._end = 0

    def get_message(self, message_id: int) -> Message | None:
        """Return the message that has the given message ID, if it is cached."""
        index = self._message_id_mapping.get(message_id, None)
        return self._messages[index] if index is not None else None

    def get_message_metadata(self, message_id: int) -> dict | None:
        """Return the metadata of the message that has the given message ID, if it is cached."""
        return self._message_metadata.get(message_id, None)

    def update(self, message: Message, *, metadata: dict | None = None) -> bool:
        """
        Update a cached message with new contents.

        Return True if the given message had a matching ID in the cache.
        """
        index = self._message_id_mapping.get(message.id, None)
        if index is None:
            return False
        self._messages[index] = message
        if metadata is not None:
            self._message_metadata[message.id] = metadata
        return True

    def __contains__(self, message_id: int) -> bool:
        """Return True if the cache contains a message with the given ID ."""
        return message_id in self._message_id_mapping

    def __getitem__(self, item: int | slice) -> Message | list[Message]:
        """
        Return the message(s) in the index or slice provided.

        This method makes the circular buffer implementation transparent to the user.
        Providing 0 will return the message at the position perceived by the user to be the beginning of the cache,
        meaning at `self._start`.
        """
        # Keep in mind that for the modulo operator used throughout this function, Python modulo behaves similarly when
        # the left operand is negative. E.g -1 % 5 == 4, because the closest number from the bottom that wholly divides
        # by 5 is -5.
        if isinstance(item, int):
            if item >= len(self) or item < -len(self):
                raise IndexError("cache index out of range")
            return self._messages[(item + self._start) % self.maxlen]

        if isinstance(item, slice):
            length = len(self)
            start, stop, step = item.indices(length)

            # This needs to be checked explicitly now, because otherwise self._start >= self._end is a valid state.
            if (start >= stop and step >= 0) or (start <= stop and step <= 0):
                return []

            start = (start + self._start) % self.maxlen
            stop = (stop + self._start) % self.maxlen

            # Having empty cells is an implementation detail. To the user the cache contains as many elements as they
            # inserted, therefore any empty cells should be ignored. There can only be Nones at the tail.
            if step > 0:
                if (
                    (self._start < self._end and not self._start < stop <= self._end)
                    or (self._start > self._end and self._end < stop <= self._start)
                ):
                    stop = self._end
            else:
                lower_boundary = (self._start - 1) % self.maxlen
                if (
                    (self._start < self._end and not self._start - 1 <= stop < self._end)
                    or (self._start > self._end and self._end < stop < lower_boundary)
                ):
                    stop = lower_boundary

            if (start < stop and step > 0) or (start > stop and step < 0):
                return self._messages[start:stop:step]
            # step != 1 may require a start offset in the second slicing.
            if step > 0:
                offset = ceil((self.maxlen - start) / step) * step + start - self.maxlen
                return self._messages[start::step] + self._messages[offset:stop:step]
            offset = ceil((start + 1) / -step) * -step - start - 1
            return self._messages[start::step] + self._messages[self.maxlen - 1 - offset:stop:step]

        raise TypeError(f"cache indices must be integers or slices, not {type(item)}")

    def __iter__(self) -> t.Iterator[Message]:
        if self._is_empty():
            return

        if self._start < self._end:
            yield from self._messages[self._start:self._end]
        else:
            yield from self._messages[self._start:]
            yield from self._messages[:self._end]

    def __len__(self):
        """Get the number of non-empty cells in the cache."""
        if self._is_empty():
            return 0
        if self._end > self._start:
            return self._end - self._start
        return self.maxlen - self._start + self._end

    def _is_empty(self) -> bool:
        """Return True if the cache has no messages."""
        return self._messages[self._start] is None

    def _is_full(self) -> bool:
        """Return True if every cell in the cache already contains a message."""
        return self._messages[self._end] is not None
