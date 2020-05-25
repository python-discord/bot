import inspect
import typing
import unittest

from bot import constants


def is_annotation_instance(value: typing.Any, annotation: typing.Any) -> bool:
    """
    Return True if `value` is an instance of the type represented by `annotation`.

    This doesn't account for things like Unions or checking for homogenous types in collections.
    """
    origin = typing.get_origin(annotation)

    # This is done in case a bare e.g. `typing.List` is used.
    # In such case, for the assertion to pass, the type needs to be normalised to e.g. `list`.
    # `get_origin()` does this normalisation for us.
    type_ = annotation if origin is None else origin

    return isinstance(value, type_)


def is_any_instance(value: typing.Any, types: typing.Collection) -> bool:
    """Return True if `value` is an instance of any type in `types`."""
    for type_ in types:
        if is_annotation_instance(value, type_):
            return True

    return False


class ConstantsTests(unittest.TestCase):
    """Tests for our constants."""

    def test_section_configuration_matches_type_specification(self):
        """"The section annotations should match the actual types of the sections."""

        sections = (
            cls
            for (name, cls) in inspect.getmembers(constants)
            if hasattr(cls, 'section') and isinstance(cls, type)
        )
        for section in sections:
            for name, annotation in section.__annotations__.items():
                with self.subTest(section=section.__name__, name=name, annotation=annotation):
                    value = getattr(section, name)
                    origin = typing.get_origin(annotation)
                    annotation_args = typing.get_args(annotation)
                    failure_msg = f"{value} is not an instance of {annotation}"

                    if origin is typing.Union:
                        is_instance = is_any_instance(value, annotation_args)
                        self.assertTrue(is_instance, failure_msg)
                    else:
                        is_instance = is_annotation_instance(value, annotation)
                        self.assertTrue(is_instance, failure_msg)
