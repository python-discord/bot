import inspect
import typing
import unittest

from bot import constants


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
                with self.subTest(section=section, name=name, annotation=annotation):
                    value = getattr(section, name)
                    annotation_args = typing.get_args(annotation)

                    if not annotation_args:
                        self.assertIsInstance(value, annotation)
                    else:
                        origin = typing.get_origin(annotation)
                        if origin is typing.Union:
                            is_instance = any(isinstance(value, arg) for arg in annotation_args)
                            self.assertTrue(is_instance)
                        else:
                            self.skipTest(f"Validating type {annotation} is unsupported.")
