from unittest import TestCase

import pytest

from bot import pagination


class LinePaginatorTests(TestCase):
    def setUp(self):
        self.paginator = pagination.LinePaginator(prefix='', suffix='', max_size=30)

    def test_add_line_raises_on_too_long_lines(self):
        message = f"Line exceeds maximum page size {self.paginator.max_size - 2}"
        with pytest.raises(RuntimeError, match=message):
            self.paginator.add_line('x' * self.paginator.max_size)

    def test_add_line_works_on_small_lines(self):
        self.paginator.add_line('x' * (self.paginator.max_size - 3))


class ImagePaginatorTests(TestCase):
    def setUp(self):
        self.paginator = pagination.ImagePaginator()

    def test_add_image_appends_image(self):
        image = 'lemon'
        self.paginator.add_image(image)

        assert self.paginator.images == [image]
