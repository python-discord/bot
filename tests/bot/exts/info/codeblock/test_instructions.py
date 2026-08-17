import unittest
from textwrap import dedent

from bot.exts.info.codeblock import _instructions as instructions, _parsing as parsing


class ProvideBadTicksInstructionsTest(unittest.TestCase):
    def __assert_is_instructions_for_message_bad_ticks_one(self, message: str) -> None:
        code_blocks = parsing.find_faulty_code_blocks(message)
        self.assertIsNotNone(code_blocks)

        # Type narrowing
        if code_blocks is None:
            return

        code_block = next((block for block in code_blocks if block.tick != parsing.BACKTICK), None)
        self.assertIsNotNone(code_block)

        # Type narrowing
        if code_block is None:
            return

        expected_instructions_text = instructions._get_bad_ticks_message(code_block)
        self.assertIsInstance(expected_instructions_text, str)

        # Type narrowing
        if not isinstance(expected_instructions_text, str):
            return

        instructions_text = instructions.get_instructions(message)
        self.assertIsInstance(instructions_text, str)

        # Type narrowing
        if not isinstance(instructions_text, str):
            return

        self.assertEqual(instructions_text, expected_instructions_text)

    def test_should_provide_when_no_lang_spec_and_bad_ticks_are_used(self) -> None:
        message = dedent("""
        '''
        \"\"\"Docstring\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''
        """).strip()
        self.__assert_is_instructions_for_message_bad_ticks_one(message)

    def test_should_provide_when_correct_lang_spec_and_bad_ticks_are_used(self) -> None:
        message = dedent("""
        '''py
        \"\"\"Docstring\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''
        """).strip()
        self.__assert_is_instructions_for_message_bad_ticks_one(message)

    def test_should_provide_when_wrong_lang_spec_and_bad_ticks_are_used(self) -> None:
        message = dedent("""
        '''c
        \"\"\"Docstring\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''
        """).strip()
        self.__assert_is_instructions_for_message_bad_ticks_one(message)

    def test_should_provide_bad_ticks_are_used_in_two_identical_codeblocks(self) -> None:
        message = dedent("""
        '''
        \"\"\"Docstring\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''

        '''
        \"\"\"Docstring\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''
        """).strip()
        self.__assert_is_instructions_for_message_bad_ticks_one(message)
