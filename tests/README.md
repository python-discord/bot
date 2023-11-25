# Testing our Bot

Our bot is one of the most important tools we have for running our community. As we don't want that tool break, we decided that we wanted to write unit tests for it. We hope that in the future, we'll have a 100% test coverage for the bot. This guide will help you get started with writing the tests needed to achieve that.

_**Note:** This is a practical guide to getting started with writing tests for our bot, not a general introduction to writing unit tests in Python. If you're looking for a more general introduction, you can take a look at the [Additional resources](#additional-resources) section at the bottom of this page._

### Table of contents:
- [Tools](#tools)
- [Running tests](#running-tests)  
- [Writing tests](#writing-tests)
- [Mocking](#mocking)
- [Some considerations](#some-considerations)
- [Additional resources](#additional-resources)

## Tools

We are using the following modules and packages for our unit tests:

- [unittest](https://docs.python.org/3/library/unittest.html) (standard library)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html) (standard library)
- [coverage.py](https://coverage.readthedocs.io/en/stable/)
- [pytest-cov](https://pytest-cov.readthedocs.io/en/latest/index.html)

We also use the following package as a test runner:
- [pytest](https://docs.pytest.org/en/6.2.x/)

To ensure the results you obtain on your personal machine are comparable to those generated in the CI, please make sure to run your tests with the virtual environment defined by our [Poetry Project](/pyproject.toml). To run your tests with `poetry`, we've provided the following "script" shortcuts:

- `poetry run task test` will run `pytest`.
- `poetry run task test path/to/test.py` will run a specific test.
- `poetry run task test-cov` will run `pytest` with `pytest-cov`.
- `poetry run task report` will generate a coverage report of the tests you've run with `poetry run task test-cov`. If you append the `-m` flag to this command, the report will include the lines and branches not covered by tests in addition to the test coverage report.

If you want a coverage report, make sure to run the tests with `poetry run task test-cov` *first*.

## Running tests
There are multiple ways to run the tests, which one you use will be determined by your goal, and stage in development.

When actively developing, you'll most likely be working on one portion of the codebase, and as a result, won't need to run the entire test suite.
To run just one file, and save time, you can use the following command:
```shell
poetry run task test <path/to/file.py>
```

For example:
```shell
poetry run task test tests/bot/exts/test_cogs.py
```
will run the test suite in the `test_cogs` file.

If you'd like to collect coverage as well, you can append `--cov` to the command above.


If you're done and are preparing to commit and push your code, it's a good idea to run the entire test suite as a sanity check:
```shell
poetry run task test
```

## Writing tests

Since consistency is an important consideration for collaborative projects, we have written some guidelines on writing tests for the bot. In addition to these guidelines, it's a good idea to look at the existing code base for examples (e.g., [`test_converters.py`](/tests/bot/test_converters.py)).

### File and directory structure

To organize our test suite, we have chosen to mirror the directory structure of [`bot`](/bot/) in the [`tests`](/tests/) subdirectory. This makes it easy to find the relevant tests by providing a natural grouping of files. More general testing files, such as [`helpers.py`](/tests/helpers.py) are located directly in the `tests` subdirectory.

All files containing tests should have a filename starting with `test_` to make sure `unittest` will discover them. This prefix is typically followed by the name of the file the tests are written for. If needed, a test file can contain multiple test classes, both to provide structure and to be able to provide different fixtures/set-up methods for different groups of tests.

### Writing independent tests

When writing unit tests, it's really important to make sure that each test that you write runs independently from all of the other tests. This both means that the code you write for one test shouldn't influence the result of another test and that if one tests fails, the other tests should still run.

The basis for this is that when you write a test method, it should really only test a single aspect of the thing you're testing. This often means that you do not write one large test that tests "everything" that can be tested for a function, but rather that you write multiple smaller tests that each test a specific branch/path/condition of the function under scrutiny.

To make sure you're not repeating the same set-up steps in all these smaller tests, `unittest` provides fixtures that are executed before and after each test is run. In addition to test fixtures, it also provides special set-up and clean-up methods that are run before the first test in a test class or after the last test of that class has been run. For more information, see the documentation for [`unittest.TestCase`](https://docs.python.org/3/library/unittest.html#unittest.TestCase).

#### Method names and docstrings

As you can probably imagine, writing smaller, independent tests also results in a large number of tests. To make sure that it's easy to see which test does what, it is incredibly important to use good method names to identify what each test is doing. A general guideline is that the name should capture the goal of your test: What is this test method trying to assert?

In addition to good method names, it's also really important to write a good *single-line* docstring. The `unittest` module will print such a single-line docstring along with the method name in the output it gives when a test fails. This means that a good docstring that really captures the purpose of the test makes it much easier to quickly make sense of output.

#### Using self.subTest for independent subtests

Another thing that you will probably encounter is that you want to test a function against a list of input and output values. Given the section on writing independent tests, you may now be tempted to copy-paste the same test method over and over again, once for each unique value that you want to test. However, that would result in a lot of duplicate code that is hard to maintain.

Luckily, `unittest` provides a good alternative to that: the [`subTest`](https://docs.python.org/3/library/unittest.html#distinguishing-test-iterations-using-subtests) context manager. This method is often used in conjunction with a `for`-loop iterating of a collection of values that we want to test a function against and it provides two important features. First, it will make sure that if an assertion statements fails on one of the iterations, the other iterations are still run. The other important feature it provides is that it will distinguish the iterations from each other in the output.

This is an example of `TestCase.subTest` in action (taken from [`test_converters.py`](/tests/bot/test_converters.py)):

```py
    def test_tag_content_converter_for_valid(self):
        """TagContentConverter should return correct values for valid input."""
        test_values = (
            ('hello', 'hellpo'),
            ('  h ello  ', 'h ello'),
        )

        for content, expected_conversion in test_values:
            with self.subTest(content=content, expected_conversion=expected_conversion):
                conversion = asyncio.run(TagContentConverter.convert(self.context, content))
                self.assertEqual(conversion, expected_conversion)
```

It's important to note the keyword arguments we provide to the `self.subTest` context manager: These keyword arguments and their values will printed in the output when one of the subtests fail, making sure we know *which* subTest failed:

```
....................................................................
======================================================================
FAIL: test_tag_content_converter_for_valid (tests.bot.test_converters.ConverterTests) (content='hello', expected_conversion='hellpo')
TagContentConverter should return correct values for valid input.
----------------------------------------------------------------------

# ...
```

## Mocking

As we are trying to test our "units" of code independently, we want to make sure that we do not rely objects and data generated by "external" code. If we we did, then we wouldn't know if the failure we're observing was caused by the code we are actually trying to test or something external to it.


However, the features that we are trying to test often depend on those objects generated by external pieces of code. It would be difficult to test a bot command without having access to a `Context` instance. Fortunately, there's a solution for that: we use fake objects that act like the true object. We call these fake objects "mocks".

To create these mock object, we mainly use the [`unittest.mock`](https://docs.python.org/3/library/unittest.mock.html) module. In addition, we have also defined a couple of specialized mock objects that mock specific `discord.py` types (see the section on the below.).

An example of mocking is when we provide a command with a mocked version of `discord.ext.commands.Context` object instead of a real `Context` object. This makes sure we can then check (_assert_) if the `send` method of the mocked Context object was called with the correct message content (without having to send a real message to the Discord API!):

```py
import asyncio
import unittest

from bot.cogs import bot
from tests.helpers import MockBot, MockContext


class BotCogTests(unittest.TestCase):
    def test_echo_command_correctly_echoes_arguments(self):
        """Test if the `!echo <text>` command correctly echoes the content."""
        mocked_bot = MockBot()
        bot_cog = bot.Bot(mocked_bot)

        mocked_context = MockContext()

        text = "Hello! This should be echoed!"

        asyncio.run(bot_cog.echo_command.callback(bot_cog, mocked_context, text=text))

        mocked_context.send.assert_called_with(text)
```

### Mocking coroutines

By default, the `unittest.mock.Mock` and `unittest.mock.MagicMock` classes cannot mock coroutines, since the `__call__` method they provide is synchronous. The [`AsyncMock`](https://docs.python.org/3/library/unittest.mock.html#unittest.mock.AsyncMock) that has been [introduced in Python 3.8](https://docs.python.org/3.9/whatsnew/3.8.html#unittest) is an asynchronous version of `MagicMock` that can be used anywhere a coroutine is expected.

### Special mocks for some `discord.py` types

To quote Ned Batchelder, Mock objects are "automatic chameleons". This means that they will happily allow the access to any attribute or method and provide a mocked value in return. One downside to this is that if the code you are testing gets the name of the attribute wrong, your mock object will not complain and the test may still pass.

In order to avoid that, we have defined a number of Mock types in [`helpers.py`](/tests/helpers.py) that follow the specifications of the actual Discord types they are mocking. This means that trying to access an attribute or method on a mocked object that does not exist on the equivalent `discord.py` object will result in an `AttributeError`. In addition, these mocks have some sensible defaults and **pass `isinstance` checks for the types they are mocking**.

These special mocks are added when they are needed, so if you think it would be sensible to add another one, feel free to propose one in your PR.

**Note:** These mock types only "know" the attributes that are set by default when these `discord.py` types are first initialized. If you need to work with dynamically set attributes that are added after initialization, you can still explicitly mock them:

```py
import unittest.mock
from tests.helpers import MockGuild

guild = MockGuild()
guild.some_attribute = unittest.mock.MagicMock()
```

The attribute `some_attribute` will now be accessible as a `MagicMock` on the mocked object.

---

## Some considerations

Finally, there are some considerations to make when writing tests, both for writing tests in general and for writing tests for our bot in particular.

### Test coverage is a starting point

Having test coverage is a good starting point for unit testing: If a part of your code was not covered by a test, we know that we have not tested it properly. The reverse is unfortunately not true: Even if the code we are testing has 100% branch coverage, it does not mean it's fully tested or guaranteed to work.

One problem is that 100% branch coverage may be misleading if we haven't tested our code against all the realistic input it may get in production. For instance, take a look at the following `member_information` function and the test we've written for it:

```py
import datetime
import unittest
import unittest.mock


def member_information(member):
    joined = member.joined.stfptime("%d-%m-%Y") if member.joined else "unknown"
    return f"{member.name} (joined: {joined})"


class FunctionsTests(unittest.TestCase):
    def test_member_information(self):
        member = unittest.mock.Mock()
        member.name = "lemon"
        member.joined = None
        self.assertEqual(member_information(member), "lemon (joined: unknown)")
```

If you were to run this test, not only would the function pass the test, `coverage.py` will also tell us that the test provides 100% branch coverage for the function. Can you spot the bug the test suite did not catch?

The problem here is that we have only tested our function with a member object that had `None` for the `member.joined` attribute. This means that `member.joined.stfptime("%d-%m-%Y")` was never executed during our test, leading to us missing the spelling mistake in `stfptime` (it should be `strftime`).

Adding another test would not increase the test coverage we have, but it does ensure that we'll notice that this function can fail with realistic data:

```py
# (...)
class FunctionsTests(unittest.TestCase):
    # (...)
    def test_member_information_with_join_datetime(self):
        member = unittest.mock.Mock()
        member.name = "lemon"
        member.joined = datetime.datetime(year=2019, month=10, day=10)
        self.assertEqual(member_information(member), "lemon (joined: 10-10-2019)")
```

Output:
```
.E
======================================================================
ERROR: test_member_information_with_join_datetime (tests.test_functions.FunctionsTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/pydis/playground/tests/test_functions.py", line 23, in test_member_information_with_join_datetime
    self.assertEqual(member_information(member), "lemon (joined: 10-10-2019)")
  File "/home/pydis/playground/tests/test_functions.py", line 8, in member_information
    joined = member.joined.stfptime("%d-%m-%Y") if member.joined else "unknown"
AttributeError: 'datetime.datetime' object has no attribute 'stfptime'

----------------------------------------------------------------------
Ran 2 tests in 0.003s

FAILED (errors=1)
```

What's more, even if the spelling mistake would not have been there, the first test did not test if the `member_information` function formatted the `member.join` according to the output we actually want to see.

All in all, it's not only important to consider if all statements or branches were touched at least once with a test, but also if they are extensively tested in all situations that may happen in production.

### Unit Testing vs Integration Testing

Another restriction of unit testing is that it tests, well, in units. Even if we can guarantee that the units work as they should independently, we have no guarantee that they will actually work well together. Even more, while the mocking described above gives us a lot of flexibility in factoring out external code, we are work under the implicit assumption that we fully understand those external parts and utilize it correctly. What if our mocked `Context` object works with a `send` method, but `discord.py` has changed it to a `send_message` method in a recent update? It could mean our tests are passing, but the code it's testing still doesn't work in production.

The answer to this is that we also need to make sure that the individual parts come together into a working application. In addition, we will also need to make sure that the application communicates correctly with external applications. Since we currently have no automated integration tests or functional tests, that means **it's still very important to fire up the bot and test the code you've written manually** in addition to the unit tests you've written.

## Additional resources

* [Ned Batchelder's PyCon talk: Getting Started Testing](https://www.youtube.com/watch?v=FxSsnHeWQBY)
* [Corey Schafer video about unittest](https://youtu.be/6tNS--WetLI)
* [RealPython tutorial on unittest testing](https://realpython.com/python-testing/)
* [RealPython tutorial on mocking](https://realpython.com/python-mock-library/)
