import unittest
from textwrap import dedent

from bot.exts.info.codeblock import _instructions as instructions


class ProvideBadTicksInstructionsTest(unittest.TestCase):
    def __assert_instructions_are_bad_ticks_ones(
        self,
        instructions_text: str,
        wrong_ticks: str,
    ) -> None:
        self.assertIn("\\`\\`\\`", instructions_text)
        self.assertIn(wrong_ticks, instructions_text)

    def __assert_instructions_contain_no_land_instructions(
        self,
        instructions_text: str,
    ) -> None:
        self.assertIn("py", instructions_text)

    def test_should_provide_bad_ticks_and_no_land_instructions_when_no_lang_spec_and_bad_ticks_are_used(self) -> None:
        message = dedent("""
        '''
        \"\"\"A script that iterates and prints the numbers\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''
        """).strip()

        instructions_text = instructions.get_instructions(message)

        self.assertIsNotNone(instructions_text)

        # Type narrowing
        if instructions_text is None:
            return

        self.__assert_instructions_are_bad_ticks_ones(instructions_text, "'''")
        self.__assert_instructions_contain_no_land_instructions(instructions_text)

    def test_should_provide_bad_ticks_instructions_when_correct_lang_spec_and_bad_ticks_are_used(self) -> None:
        message = dedent("""
        '''py
        \"\"\"A script that iterates and prints the numbers\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''
        """).strip()

        instructions_text = instructions.get_instructions(message)

        self.assertIsNotNone(instructions_text)

        # Type narrowing
        if instructions_text is None:
            return

        self.__assert_instructions_are_bad_ticks_ones(instructions_text, "'''")

    def test_should_provide_bad_ticks_instructions_when_wrong_lang_spec_and_bad_ticks_are_used(self) -> None:
        message = dedent("""
        '''c
        \"\"\"A script that iterates and prints the numbers\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''
        """).strip()

        instructions_text = instructions.get_instructions(message)

        self.assertIsNotNone(instructions_text)

        # Type narrowing
        if instructions_text is None:
            return

        self.__assert_instructions_are_bad_ticks_ones(instructions_text, "'''")

    def test_should_provide_bad_ticks_instructions_when_bad_ticks_are_used_in_two_identical_codeblocks(self) -> None:
        message = dedent("""
        '''py
        \"\"\"Docstring\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''

        '''py
        \"\"\"Docstring\"\"\"
        numbs = [1, 2, 3]

        for numb in numbs:
            print(numb)
        '''
        """).strip()

        instructions_text = instructions.get_instructions(message)

        self.assertIsNotNone(instructions_text)

        # Type narrowing
        if instructions_text is None:
            return

        self.__assert_instructions_are_bad_ticks_ones(instructions_text, "'''")
