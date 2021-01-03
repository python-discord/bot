import unittest
from abc import ABCMeta, abstractmethod
from typing import Callable, Dict, Iterable, List, NamedTuple, Tuple

from tests.helpers import MockMessage


class DisallowedCase(NamedTuple):
    """Encapsulation for test cases expected to fail."""
    recent_messages: List[MockMessage]
    culprits: Iterable[str]
    n_violations: int


class RuleTest(unittest.IsolatedAsyncioTestCase, metaclass=ABCMeta):
    """
    Abstract class for antispam rule test cases.

    Tests for specific rules should inherit from `RuleTest` and implement
    `relevant_messages` and `get_report`. Each instance should also set the
    `apply` and `config` attributes as necessary.

    The execution of test cases can then be delegated to the `run_allowed`
    and `run_disallowed` methods.
    """

    apply: Callable  # The tested rule's apply function
    config: Dict[str, int]

    async def run_allowed(self, cases: Tuple[List[MockMessage], ...]) -> None:
        """Run all `cases` against `self.apply` expecting them to pass."""
        for recent_messages in cases:
            last_message = recent_messages[0]

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                config=self.config,
            ):
                self.assertIsNone(
                    await self.apply(last_message, recent_messages, self.config)
                )

    async def run_disallowed(self, cases: Tuple[DisallowedCase, ...]) -> None:
        """Run all `cases` against `self.apply` expecting them to fail."""
        for case in cases:
            recent_messages, culprits, n_violations = case
            last_message = recent_messages[0]
            relevant_messages = self.relevant_messages(case)
            desired_output = (
                self.get_report(case),
                culprits,
                relevant_messages,
            )

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                relevant_messages=relevant_messages,
                n_violations=n_violations,
                config=self.config,
            ):
                self.assertTupleEqual(
                    await self.apply(last_message, recent_messages, self.config),
                    desired_output,
                )

    @abstractmethod
    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        """Give expected relevant messages for `case`."""
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def get_report(self, case: DisallowedCase) -> str:
        """Give expected error report for `case`."""
        raise NotImplementedError  # pragma: no cover
