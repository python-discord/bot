# perlin sneks!
import io
import math
import random
from typing import Tuple

from PIL.ImageDraw import Image, ImageDraw

from bot.utils.snakes import perlin

DEFAULT_SNAKE_COLOR: int = 0x15c7ea
DEFAULT_BACKGROUND_COLOR: int = 0
DEFAULT_IMAGE_DIMENSIONS: Tuple[int] = (200, 200)
DEFAULT_SNAKE_LENGTH: int = 22
DEFAULT_SNAKE_WIDTH: int = 8
DEFAULT_SEGMENT_LENGTH_RANGE: Tuple[int] = (7, 10)
DEFAULT_IMAGE_MARGINS: Tuple[int] = (50, 50)
DEFAULT_TEXT: str = "snek\nit\nup"
DEFAULT_TEXT_POSITION: Tuple[int] = (
    10,
    10
)
DEFAULT_TEXT_COLOR: int = 0xf2ea15

X = 0
Y = 1
ANGLE_RANGE = math.pi * 2


def create_snek_frame(
        perlin_factory: perlin.PerlinNoiseFactory, perlin_lookup_vertical_shift: float = 0,
        image_dimensions: Tuple[int] = DEFAULT_IMAGE_DIMENSIONS, image_margins: Tuple[int] = DEFAULT_IMAGE_MARGINS,
        snake_length: int = DEFAULT_SNAKE_LENGTH,
        snake_color: int = DEFAULT_SNAKE_COLOR, bg_color: int = DEFAULT_BACKGROUND_COLOR,
        segment_length_range: Tuple[int] = DEFAULT_SEGMENT_LENGTH_RANGE, snake_width: int = DEFAULT_SNAKE_WIDTH,
        text: str = DEFAULT_TEXT, text_position: Tuple[int] = DEFAULT_TEXT_POSITION,
        text_color: Tuple[int] = DEFAULT_TEXT_COLOR
) -> Image:
    """
    Creates a single random snek frame using Perlin noise.
    :param perlin_factory: the perlin noise factory used. Required.
    :param perlin_lookup_vertical_shift: the Perlin noise shift in the Y-dimension for this frame
    :param image_dimensions: the size of the output image.
    :param image_margins: the margins to respect inside of the image.
    :param snake_length: the length of the snake, in segments.
    :param snake_color: the color of the snake.
    :param bg_color: the background color.
    :param segment_length_range: the range of the segment length. Values will be generated inside this range, including
                                 the bounds.
    :param snake_width: the width of the snek, in pixels.
    :param text: the text to display with the snek. Set to None for no text.
    :param text_position: the position of the text.
    :param text_color: the color of the text.
    :return: a PIL image, representing a single frame.
    """
    start_x = random.randint(image_margins[X], image_dimensions[X] - image_margins[X])
    start_y = random.randint(image_margins[Y], image_dimensions[Y] - image_margins[Y])
    points = [(start_x, start_y)]

    for index in range(0, snake_length):
        angle = perlin_factory.get_plain_noise(
            ((1 / (snake_length + 1)) * (index + 1)) + perlin_lookup_vertical_shift
        ) * ANGLE_RANGE
        current_point = points[index]
        segment_length = random.randint(segment_length_range[0], segment_length_range[1])
        points.append((
            current_point[X] + segment_length * math.cos(angle),
            current_point[Y] + segment_length * math.sin(angle)
        ))

    # normalize bounds
    min_dimensions = [start_x, start_y]
    max_dimensions = [start_x, start_y]
    for point in points:
        min_dimensions[X] = min(point[X], min_dimensions[X])
        min_dimensions[Y] = min(point[Y], min_dimensions[Y])
        max_dimensions[X] = max(point[X], max_dimensions[X])
        max_dimensions[Y] = max(point[Y], max_dimensions[Y])

    # shift towards middle
    dimension_range = (max_dimensions[X] - min_dimensions[X], max_dimensions[Y] - min_dimensions[Y])
    shift = (
        image_dimensions[X] / 2 - (dimension_range[X] / 2 + min_dimensions[X]),
        image_dimensions[Y] / 2 - (dimension_range[Y] / 2 + min_dimensions[Y])
    )

    image = Image.new(mode='RGB', size=image_dimensions, color=bg_color)
    draw = ImageDraw(image)
    for index in range(1, len(points)):
        point = points[index]
        previous = points[index - 1]
        draw.line(
            (
                shift[X] + previous[X],
                shift[Y] + previous[Y],
                shift[X] + point[X],
                shift[Y] + point[Y]
            ),
            width=snake_width,
            fill=snake_color
        )
    if text is not None:
        draw.multiline_text(text_position, text, fill=text_color)
    del draw
    return image


def frame_to_png_bytes(image: Image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()
