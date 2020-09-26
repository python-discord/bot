from unittest import TestCase

from bot import pagination


class LinePaginatorTests(TestCase):
    """Tests functionality of the `LinePaginator`."""

    def setUp(self):
        """Create a paginator for the test method."""
        self.paginator = pagination.LinePaginator(prefix='', suffix='', max_size=30,
                                                  scale_to_size=50)

    def test_add_line_works_on_small_lines(self):
        """`add_line` should allow small lines to be added."""
        self.paginator.add_line('x' * (self.paginator.max_size - 3))
        # Note that the page isn't added to _pages until it's full.
        self.assertEqual(len(self.paginator._pages), 0)

    def test_add_line_works_on_long_lines(self):
        """After additional lines after `max_size` is exceeded should go on the next page."""
        self.paginator.add_line('x' * self.paginator.max_size)
        self.assertEqual(len(self.paginator._pages), 0)

        # Any additional lines should start a new page after `max_size` is exceeded.
        self.paginator.add_line('x')
        self.assertEqual(len(self.paginator._pages), 1)

    def test_add_line_continuation(self):
        """When `scale_to_size` is exceeded, remaining words should be split onto the next page."""
        self.paginator.add_line('zyz ' * (self.paginator.scale_to_size//4 + 1))
        self.assertEqual(len(self.paginator._pages), 1)

    def test_add_line_no_continuation(self):
        """If adding a new line to an existing page would exceed `max_size`, it should start a new
        page rather than using continuation.
        """
        self.paginator.add_line('z' * (self.paginator.max_size - 3))
        self.paginator.add_line('z')
        self.assertEqual(len(self.paginator._pages), 1)

    def test_add_line_truncates_very_long_words(self):
        """`add_line` should truncate if a single long word exceeds `scale_to_size`."""
        self.paginator.add_line('x' * (self.paginator.scale_to_size + 1))
        # Note: item at index 1 is the truncated line, index 0 is prefix
        self.assertEqual(self.paginator._current_page[1], 'x' * self.paginator.scale_to_size)
