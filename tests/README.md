# Testing our Bot

Our bot is one of the most important tools we have to help us run our community. To make sure that tool doesn't break, we've decided to start writing unit tests for it. It is our goal to provide it with 100% test coverage in the future. This guide will help you get started with writing the tests needed to achieve that.

_**Note:** This is a practical guide to getting started with writing tests for our bot, not a general introduction to writing unit tests in Python. If you're looking for a more general introduction, you may like Corey Schafer's [Python Tutorial: Unit Testing Your Code with the unittest Module](https://www.youtube.com/watch?v=6tNS--WetLI) or Ned Batchelder's PyCon talk [Getting Started Testing](https://www.youtube.com/watch?v=FxSsnHeWQBY)._

## Tools

We are using the following modules and packages for our unit tests:

- [unittest](https://docs.python.org/3/library/unittest.html) (standard library)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html) (standard library)
- [coverage.py](https://coverage.readthedocs.io/en/stable/)

To ensure the results you obtain on your personal machine are comparable to those in the Azure pipeline, please make sure to run your tests with the virtual environment defined by our [Pipfile](/Pipfile). To run your tests with `pipenv`, we've provided two "scripts" shortcuts:

1. `pipenv run test` will run `unittest` with `coverage.py`
2. `pipenv run report` will generate a coverage report of the tests you've run with `pipenv run test`. If you append the `-m` flag to this command, the report will include the lines and branches not covered by tests in addition to the test coverage report.

**Note:** If you want a coverage report, make sure to run the tests with `pipenv run test` *first*.

## Writing tests

Since our bot is a collaborative, community project, it's important to take a couple of things into when writing tests. This ensures that our test suite is consistent and that everyone understands the tests someone else has written.

### File and directory structure

To organize our test suite, we have chosen to mirror the directory structure of [`bot`](/bot/) in the [`tests`](/tests/) subdirectory. This makes it easy to find the relevant tests by providing a natural grouping of files. More general files, such as [`helpers.py`](/tests/helpers.py) are located directly in the `tests` subdirectory.

All files containing tests should have a filename starting with `test_` to make sure `unittest` will discover them. This prefix is typically followed by the name of the file the tests are written for. If needed, a test file can contain multiple test classes, both to provide structure and to be able to provide different fixtures/set-up methods for different groups of tests.

### Writing individual and independent tests

When writing individual test methods, it is important to make sure that each test tests its own *independent* unit. In general, this means that you don't write one large test method that tests every possible branch/part/condition relevant to your function, but rather write separate test methods for each one. The reason is that this will make sure that if one test fails, the rest of the tests will still run and we feedback on exactly which parts are and which are not working correctly. (However, the [DRY-principle](https://en.wikipedia.org/wiki/Don%27t_repeat_yourself) also applies to tests, see the `Using self.subTest for independent subtests` section.)

#### Method names and docstrings

It's very important that the output of failing tests is easy to understand. That's why it is important to give your test methods a descriptive name that tells us what the failing test was testing. In addition, since **single-line** docstrings will be printed in the output along with the method name, it's also important to add a good single-line docstring that summarizes the purpose of the test to your test method.

#### Using self.subTest for independent subtests

Since it's important to make sure all of our tests are independent from each other, you may be tempted to copy-paste your test methods to test a function against a number of different input and output parameters. Luckily, `unittest` provides a better a better of doing that: [`subtests`](https://docs.python.org/3/library/unittest.html#distinguishing-test-iterations-using-subtests). 

By using the `subTest` context manager, we can perform multiple independent subtests within one test method (e.g., by having a loop for the various inputs we want to test). Using this context manager ensures the test will be run independently and that, if one of them fails, the rest of the subtests are still executed. (Normally, a test function stops once the first exception, including `AssertionError`, is raised.)

An example (taken from [`test_converters.py`](/tests/bot/test_converters.py)):

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

# Snipped to save vertical space
```

## Mocking

Since we are testing independent "units" of code, we sometimes need to provide "fake" versions of objects generated by code external to the unit we are trying to test to make sure we're truly testing independently from other units of code. We call these "fake objects" mocks. We mainly use the [`unittest.mock`](https://docs.python.org/3/library/unittest.mock.html) module to create these mock objects, but we also have a couple special mock types defined in [`helpers.py`](/tests/helpers.py). 

An example of mocking is when we provide a command with a mocked version of `discord.ext.commands.Context` object instead of a real `Context` object and then assert if the `send` method of the mocked version was called with the right message content by the command function:

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

By default, `unittest.mock.Mock` and `unittest.mock.MagicMock` can't mock coroutines, since the `__call__` method they provide is synchronous. In anticipation of the `AsyncMock` that will be [introduced in Python 3.8](https://docs.python.org/3.9/whatsnew/3.8.html#unittest), we have added an `AsyncMock` helper to [`helpers.py`](/tests/helpers.py). Do note that this drop-in replacement only implements an asynchronous `__call__` method, not the additional assertions that will come with the new `AsyncMock` type in Python 3.8. 

### Special mocks for some `discord.py` types

To quote Ned Batchelder, Mock objects are "automatic chameleons". This means that they will happily allow the access to any attribute or method and provide a mocked value in return. One downside to this is that if the code you are testing gets the name of the attribute wrong, your mock object will not complain and the test may still pass.

In order to avoid that, we have defined a number of Mock types in [`helpers.py`](/tests/helpers.py) that follow the specifications of the actual Discord types they are mocking. This means that trying to access an attribute or method on a mocked object that does not exist by default on the equivalent `discord.py` object will result in an `AttributeError`. In addition, these mocks have some sensible defaults and **pass `isinstance` checks for the types they are mocking**. 

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

### Unit Testing vs Integration Testing

Another restriction of unit testing is that it tests in, well, units. Even if we can guarantee that the units work as they should independently, we have no guarantee that they will actually work well together. Even more, while the mocking described above gives us a lot of flexibility in factoring out external code, we work under the implicit assumption of understanding and utilizing those external objects correctly. So, in addition to testing the parts separately, we also need to test if the parts integrate correctly into a single application.

We currently have no automated integration tests or functional tests, so **it's still very important to fire up the bot and test the code you've written manually** in addition to the unit tests you've written.
