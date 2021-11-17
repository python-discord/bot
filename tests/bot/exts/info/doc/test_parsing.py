from unittest import TestCase

from bot.exts.info.doc import _parsing as parsing


class SignatureSplitter(TestCase):
    def test_basic_split(self):
        test_cases = (
            ("0,0,0", ["0", "0", "0"]),
            ("0,a=0,a=0", ["0", "a=0", "a=0"]),
        )
        self._run_tests(test_cases)

    def test_commas_ignored_in_brackets(self):
        test_cases = (
            ("0,[0,0],0,[0,0],0", ["0", "[0,0]", "0", "[0,0]", "0"]),
            ("(0,),0,(0,(0,),0),0", ["(0,)", "0", "(0,(0,),0)", "0"]),
        )
        self._run_tests(test_cases)

    def test_mixed_brackets(self):
        tests_cases = (
            ("[0,{0},0],0,{0:0},0", ["[0,{0},0]", "0", "{0:0}", "0"]),
            ("([0],0,0),0,(0,0),0", ["([0],0,0)", "0", "(0,0)", "0"]),
            ("([(0,),(0,)],0),0", ["([(0,),(0,)],0)", "0"]),
        )
        self._run_tests(tests_cases)

    def test_string_contents_ignored(self):
        test_cases = (
            ("'0,0',0,',',0", ["'0,0'", "0", "','", "0"]),
            ("0,[']',0],0", ["0", "[']',0]", "0"]),
            ("{0,0,'}}',0,'{'},0", ["{0,0,'}}',0,'{'}", "0"]),
        )
        self._run_tests(test_cases)

    def test_mixed_quotes(self):
        test_cases = (
            ("\"0',0',\",'0,0',0", ["\"0',0',\"", "'0,0'", "0"]),
            ("\",',\",'\",',0", ['",\',"', "'\",'", "0"]),
        )
        self._run_tests(test_cases)

    def test_quote_escaped(self):
        test_cases = (
            (r"'\',','\\',0", [r"'\','", r"'\\'", "0"]),
            (r"'0\',0\\\'\\',0", [r"'0\',0\\\'\\'", "0"]),
        )
        self._run_tests(test_cases)

    def test_real_signatures(self):
        test_cases = (
            ("start, stop[, step]", ["start", " stop[, step]"]),
            (
                "object=b'', encoding='utf-8', errors='strict'",
                ["object=b''", " encoding='utf-8'", " errors='strict'"],
            ),
            (
                "typename, field_names, *, rename=False, defaults=None, module=None",
                [
                    "typename",
                    " field_names",
                    " *",
                    " rename=False",
                    " defaults=None",
                    " module=None",
                ],
            ),
        )
        self._run_tests(test_cases)

    def _run_tests(self, test_cases):
        for input_string, expected_output in test_cases:
            with self.subTest(input_string=input_string):
                self.assertEqual(
                    list(parsing._split_parameters(input_string)), expected_output
                )
