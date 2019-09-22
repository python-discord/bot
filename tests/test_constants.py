import inspect

import pytest

from bot import constants


@pytest.mark.parametrize(
    'section',
    (
        cls
        for (name, cls) in inspect.getmembers(constants)
        if hasattr(cls, 'section') and isinstance(cls, type)
    )
)
def test_section_configuration_matches_typespec(section):
    for (name, annotation) in section.__annotations__.items():
        value = getattr(section, name)

        if getattr(annotation, '_name', None) in ('Dict', 'List'):
            pytest.skip("Cannot validate containers yet")

        assert isinstance(value, annotation)
