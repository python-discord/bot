import inspect
import unittest

from bot import constants


class ConstantsTests(unittest.TestCase):
    """Tests for our constants."""

    @unittest.expectedFailure
    def test_section_configuration_matches_type_specification(self):
        """The section annotations should match the actual types of the sections."""

        sections = (
            cls
            for (name, cls) in inspect.getmembers(constants)
            if hasattr(cls, 'section') and isinstance(cls, type)
        )
        for section in sections:
            for name, annotation in section.__annotations__.items():
                with self.subTest(section=section, name=name, annotation=annotation):
                    value = getattr(section, name)

                    if getattr(annotation, '_name', None) in ('Dict', 'List'):
                        self.skipTest("Cannot validate containers yet.")

                    self.assertIsInstance(value, annotation)
