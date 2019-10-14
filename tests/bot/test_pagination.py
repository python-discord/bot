from unittest import TestCase

from bot import pagination


class LinePaginatorTests(TestCase):
    """Tests functionality of the `LinePaginator`."""

    def setUp(self):
        """Create a paginator for the test method."""
        self.paginator = pagination.LinePaginator(prefix='', suffix='', max_size=30)

    def test_add_line_raises_on_too_long_lines(self):
        """`add_line` should raise a `RuntimeError` for too long lines."""
        message = f"Line exceeds maximum page size {self.paginator.max_size - 2}"
        with self.assertRaises(RuntimeError, msg=message):
            self.paginator.add_line('x' * self.paginator.max_size)

    def test_add_line_works_on_small_lines(self):
        """`add_line` should allow small lines to be added."""
        self.paginator.add_line('x' * (self.paginator.max_size - 3))


class ImagePaginatorTests(TestCase):
    """Tests functionality of the `ImagePaginator`."""

    def setUp(self):
        """Create a paginator for the test method."""
        self.paginator = pagination.ImagePaginator()

    def test_add_image_appends_image(self):
        """`add_image` appends the image to the image list."""
        image = 'lemon'
        self.paginator.add_image(image)

        assert self.paginator.images == [image]
