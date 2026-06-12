import unittest

from bot.exts.info.codeblock import _parsing as parsing


class FindFaultyCodeblocksTest(unittest.TestCase):
    def test_should_recognize_missing_language(self):
        message = """```
        x = 4
        y = 2
        print("abc")
        ```"""
        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 1)

    def test_should_recognize_contained_codeblock(self):
        message = """'
        wouldn't it be easier to do:
        ```py
        say_hi = lambda:
            print('hello')
            print('world')
        say_hi()

        '
        ```

        '"""
        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNone(faulty_code_blocks)

    def test_should_recognize_contained_codeblock_even_if_that_breaks_formatting(self):
        message = """```
        ```py
        x = 4
        y = 3
        z = 2
        print("abc")
        ```
        ```
        """
        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNone(faulty_code_blocks)

    def test_should_not_recognize_normal_single_quotes(self):
        """normal single quotes refers to single quotes that appear normally in text,
        like for example in "I'll", "We're", etc."""
        message = """I'm writing line 1
        and we're writing line 2
        we'll also be checking another of those
        and some odd 'variations
        isn't it beautiful?"""

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 0)

    def test_should_not_recognize_quoting_single_quotes(self):
        message = """ 'I am doing a long quote.
        Sure, I could just use the > character
        for correct quoting
        but whatever...
        End of quote' """

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 0)


    def test_should_not_recognize_normal_double_quotes(self):
        """normal double quotes refer to double quotes that appear normally in text to quote something"""
        message = """ "I am doing a long quote.
        Sure, I could just use the > character
        for correct quoting
        but whatever...
        End of quote" """

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 0)

    def test_should_not_recognize_normal_double_quotes_python_text(self):
        message = """ "python is a great language
        great
        great
        great language
        enough lines?
        yes" """

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 0)

    def test_should_recognize_single_backtick_no_language(self):
        message = """`
        x = 4
        y = 3
        z = 2
        print("abc")
        `"""

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 1)

    def test_should_recognize_single_backtick_with_language(self):
        message = """`py
        x = 4
        y = 3
        z = 2
        print("abc")
        `"""

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 1)

    def test_should_recognize_single_single_quote_with_py_language(self):
        message = """'py
        x = 4
        y = 3
        z = 2
        print("abc")
        '"""

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 1)

    def test_should_recognize_single_single_quote_with_python_language(self):
        message = """'python
        x = 4
        y = 3
        z = 2
        print("abc")
        '"""

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 1)

    def test_should_recognize_wrong_number_of_backticks(self):
        message = """``py
        x = 4
        y = 3
        z = 2
        print("abc")
        ``"""

        faulty_code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(faulty_code_blocks)
        self.assertEqual(len(faulty_code_blocks), 1)
