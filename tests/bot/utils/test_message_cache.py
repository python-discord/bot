import unittest

from bot.utils.message_cache import MessageCache
from tests.helpers import MockMessage


# noinspection SpellCheckingInspection
class TestMessageCache(unittest.TestCase):
    """Tests for the MessageCache class in the `bot.utils.caching` module."""

    def test_first_append_sets_the_first_value(self):
        """Test if the first append adds the message to the first cell."""
        cache = MessageCache(maxlen=10)
        message = MockMessage()

        cache.append(message)

        self.assertEqual(cache[0], message)

    def test_append_adds_in_the_right_order(self):
        """Test if two appends are added in the same order if newest_first is False, or in reverse order otherwise."""
        messages = [MockMessage(), MockMessage()]

        cache = MessageCache(maxlen=10, newest_first=False)
        for msg in messages:
            cache.append(msg)
        self.assertListEqual(messages, list(cache))

        cache = MessageCache(maxlen=10, newest_first=True)
        for msg in messages:
            cache.append(msg)
        self.assertListEqual(messages[::-1], list(cache))

    def test_appending_over_maxlen_removes_oldest(self):
        """Test if three appends to a 2-cell cache leave the two newest messages."""
        cache = MessageCache(maxlen=2)
        messages = [MockMessage() for _ in range(3)]

        for msg in messages:
            cache.append(msg)

        self.assertListEqual(messages[1:], list(cache))

    def test_appending_over_maxlen_with_newest_first_removes_oldest(self):
        """Test if three appends to a 2-cell cache leave the two newest messages if newest_first is True."""
        cache = MessageCache(maxlen=2, newest_first=True)
        messages = [MockMessage() for _ in range(3)]

        for msg in messages:
            cache.append(msg)

        self.assertListEqual(messages[:0:-1], list(cache))

    def test_pop_removes_from_the_end(self):
        """Test if a pop removes the right-most message."""
        cache = MessageCache(maxlen=3)
        messages = [MockMessage() for _ in range(3)]

        for msg in messages:
            cache.append(msg)
        msg = cache.pop()

        self.assertEqual(msg, messages[-1])
        self.assertListEqual(messages[:-1], list(cache))

    def test_popleft_removes_from_the_beginning(self):
        """Test if a popleft removes the left-most message."""
        cache = MessageCache(maxlen=3)
        messages = [MockMessage() for _ in range(3)]

        for msg in messages:
            cache.append(msg)
        msg = cache.popleft()

        self.assertEqual(msg, messages[0])
        self.assertListEqual(messages[1:], list(cache))

    def test_clear(self):
        """Test if a clear makes the cache empty."""
        cache = MessageCache(maxlen=5)
        messages = [MockMessage() for _ in range(3)]

        for msg in messages:
            cache.append(msg)
        cache.clear()

        self.assertListEqual(list(cache), [])
        self.assertEqual(len(cache), 0)

    def test_get_message_returns_the_message(self):
        """Test if get_message returns the cached message."""
        cache = MessageCache(maxlen=5)
        message = MockMessage(id=1234)

        cache.append(message)

        self.assertEqual(cache.get_message(1234), message)

    def test_get_message_returns_none(self):
        """Test if get_message returns None for an ID of a non-cached message."""
        cache = MessageCache(maxlen=5)
        message = MockMessage(id=1234)

        cache.append(message)

        self.assertIsNone(cache.get_message(4321))

    def test_update_replaces_old_element(self):
        """Test if an update replaced the old message with the same ID."""
        cache = MessageCache(maxlen=5)
        message = MockMessage(id=1234)

        cache.append(message)
        message = MockMessage(id=1234)
        cache.update(message)

        self.assertIs(cache.get_message(1234), message)
        self.assertEqual(len(cache), 1)

    def test_contains_returns_true_for_cached_message(self):
        """Test if contains returns True for an ID of a cached message."""
        cache = MessageCache(maxlen=5)
        message = MockMessage(id=1234)

        cache.append(message)

        self.assertIn(1234, cache)

    def test_contains_returns_false_for_non_cached_message(self):
        """Test if contains returns False for an ID of a non-cached message."""
        cache = MessageCache(maxlen=5)
        message = MockMessage(id=1234)

        cache.append(message)

        self.assertNotIn(4321, cache)

    def test_indexing(self):
        """Test if the cache returns the correct messages by index."""
        cache = MessageCache(maxlen=5)
        messages = [MockMessage() for _ in range(5)]

        for msg in messages:
            cache.append(msg)

        for current_loop in range(-5, 5):
            with self.subTest(current_loop=current_loop):
                self.assertEqual(cache[current_loop], messages[current_loop])

    def test_bad_index_raises_index_error(self):
        """Test if the cache raises IndexError for invalid indices."""
        cache = MessageCache(maxlen=5)
        messages = [MockMessage() for _ in range(3)]
        test_cases = (-10, -4, 3, 4, 5)

        for msg in messages:
            cache.append(msg)

        for current_loop in test_cases:
            with self.subTest(current_loop=current_loop), self.assertRaises(IndexError):
                cache[current_loop]

    def test_slicing_with_unfilled_cache(self):
        """Test if slicing returns the correct messages if the cache is not yet fully filled."""
        sizes = (5, 10, 55, 101)

        slices = (
            slice(None), slice(2, None), slice(None, 2), slice(None, None, 2), slice(None, None, 3), slice(-1, 2),
            slice(-1, 3000), slice(-3, -1), slice(-10, 3), slice(-10, 4, 2), slice(None, None, -1), slice(None, 3, -2),
            slice(None, None, -3), slice(-1, -10, -2), slice(-3, -7, -1)
        )

        for size in sizes:
            cache = MessageCache(maxlen=size)
            messages = [MockMessage() for _ in range(size // 3 * 2)]

            for msg in messages:
                cache.append(msg)

            for slice_ in slices:
                with self.subTest(current_loop=(size, slice_)):
                    self.assertListEqual(cache[slice_], messages[slice_])

    def test_slicing_with_overfilled_cache(self):
        """Test if slicing returns the correct messages if the cache was appended with more messages it can contain."""
        sizes = (5, 10, 55, 101)

        slices = (
            slice(None), slice(2, None), slice(None, 2), slice(None, None, 2), slice(None, None, 3), slice(-1, 2),
            slice(-1, 3000), slice(-3, -1), slice(-10, 3), slice(-10, 4, 2), slice(None, None, -1), slice(None, 3, -2),
            slice(None, None, -3), slice(-1, -10, -2), slice(-3, -7, -1)
        )

        for size in sizes:
            cache = MessageCache(maxlen=size)
            messages = [MockMessage() for _ in range(size * 3 // 2)]

            for msg in messages:
                cache.append(msg)
            messages = messages[size // 2:]

            for slice_ in slices:
                with self.subTest(current_loop=(size, slice_)):
                    self.assertListEqual(cache[slice_], messages[slice_])

    def test_length(self):
        """Test if len returns the correct number of items in the cache."""
        cache = MessageCache(maxlen=5)

        for current_loop in range(10):
            with self.subTest(current_loop=current_loop):
                self.assertEqual(len(cache), min(current_loop, 5))
                cache.append(MockMessage())
