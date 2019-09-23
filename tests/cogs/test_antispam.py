import pytest

from bot.cogs import antispam


def test_default_antispam_config_is_valid():
    validation_errors = antispam.validate_config()
    assert not validation_errors


@pytest.mark.parametrize(
    ('config', 'expected'),
    (
        (
            {'invalid-rule': {}},
            {'invalid-rule': "`invalid-rule` is not recognized as an antispam rule."}
        ),
        (
            {'burst': {'interval': 10}},
            {'burst': "Key `max` is required but not set for rule `burst`"}
        ),
        (
            {'burst': {'max': 10}},
            {'burst': "Key `interval` is required but not set for rule `burst`"}
        )
    )
)
def test_invalid_antispam_config_returns_validation_errors(config, expected):
    validation_errors = antispam.validate_config(config)
    assert validation_errors == expected
