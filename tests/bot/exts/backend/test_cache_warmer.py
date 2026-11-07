import unittest
from collections import deque
from types import SimpleNamespace

from bot.exts.backend.cache_warmer import merge_into_cache


def msgs(*ids: int) -> list[SimpleNamespace]:
    return [SimpleNamespace(id=i) for i in ids]


def ids(cache: deque) -> list[int]:
    return [message.id for message in cache]


class MergeIntoCacheTests(unittest.TestCase):
    """Tests for `merge_into_cache`."""

    def test_older_messages_are_added_in_chronological_order(self):
        cache = deque(msgs(10, 11), maxlen=10)
        added = merge_into_cache(cache, msgs(3, 1, 2, 5))
        self.assertEqual(added, 4)
        self.assertEqual(ids(cache), [1, 2, 3, 5, 10, 11])

    def test_empty_cache_is_filled(self):
        cache = deque(maxlen=10)
        merge_into_cache(cache, msgs(2, 1))
        self.assertEqual(ids(cache), [1, 2])

    def test_duplicates_and_newer_messages_are_skipped(self):
        cache = deque(msgs(10, 11), maxlen=10)
        added = merge_into_cache(cache, msgs(10, 12, 4, 4))
        self.assertEqual(added, 1)
        self.assertEqual(ids(cache), [4, 10, 11])

    def test_only_the_newest_messages_fit_and_none_are_dropped(self):
        cache = deque(msgs(10, 11), maxlen=5)
        added = merge_into_cache(cache, msgs(1, 2, 3, 4, 5))
        self.assertEqual(added, 3)
        self.assertEqual(ids(cache), [3, 4, 5, 10, 11])

    def test_full_cache_is_unchanged(self):
        cache = deque(msgs(10, 11), maxlen=2)
        self.assertEqual(merge_into_cache(cache, msgs(1, 2)), 0)
        self.assertEqual(ids(cache), [10, 11])
