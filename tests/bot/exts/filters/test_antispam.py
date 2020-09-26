import unittest

from bot.exts.filters import antispam


class AntispamConfigurationValidationTests(unittest.TestCase):
    """Tests validation of the antispam cog configuration."""

    def test_default_antispam_config_is_valid(self):
        """The default antispam configuration is valid."""
        validation_errors = antispam.validate_config()
        self.assertEqual(validation_errors, {})

    def test_unknown_rule_returns_error(self):
        """Configuring an unknown rule returns an error."""
        self.assertEqual(
            antispam.validate_config({'invalid-rule': {}}),
            {'invalid-rule': "`invalid-rule` is not recognized as an antispam rule."}
        )

    def test_missing_keys_returns_error(self):
        """Not configuring required keys returns an error."""
        keys = (('interval', 'max'), ('max', 'interval'))
        for configured_key, unconfigured_key in keys:
            with self.subTest(
                configured_key=configured_key,
                unconfigured_key=unconfigured_key
            ):
                config = {'burst': {configured_key: 10}}
                error = f"Key `{unconfigured_key}` is required but not set for rule `burst`"

                self.assertEqual(
                    antispam.validate_config(config),
                    {'burst': error}
                )
