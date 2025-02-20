# Report for assignment 3

This project is an experiment in complexity and coverage metrics, based on [Discord bot](https://github.com/python-discord/bot). The goals are to get an understanding and appreciation of the benefits and drawbacks of metrics and their tools, and to create new test cases or to enhance existing tests that improve statement or branch coverage.

## Onboarding experience

1. I don't have to install many additional tools to build the software except Poetry.
2. Poetry is a widely-used Python packaging and dependency management tool, well documented on the official website.
3. Other components are installed automatically by the Poetry commands.
4. The build concludes automatically without errors.
5. After setting up a Discord test server and bot account, configuring the bot, examples and tests run well on my system (Ubuntu 22.04).

We finally decide to continue on Discord bot.

## Complexity

### on_command_error()

Function: `on_command_error@65-149@./bot/exts/backend/error_handler.py`

1. The CC is 20. Everyone gets the same result and nothing is unclear. The result given by Lizard is also 20, same as ours.
2. This function is with 76 NLOCs and CC of 20. It is both complex and long.
3. This function is used to handle the errors. There are lots of `if` statements to get the type of the error and handle the possible exception, which is tightly related to the high CC.
4. Exceptions in Python are taken into account by Lizard. The CC is counted 1 more time for each except block.
5. The documentation of the function is pretty clear as comments, but it does not cover all the branches in the function (Some of these branches are self-explained by function and variable names).

## Refactoring

Plan for refactoring complex code:

Estimated impact of refactoring (lower CC, but other drawbacks?).

Carried out refactoring (optional, P+):

git diff ...

## Coverage

### Tools

Discord bot is already integrated with coverage tool `Coverage.py`, and the commands to use it are well documented in `./tests/README.md`. So we don't need to use `Coverage.py` directly. Discord bot uses Pytest to execute test cases, and `Coverage.py` is compatible with Pytest. So it is easy to integrate it with the build environment.

### Own coverage tool

Branch [feat/1-cov-error-handler](https://github.com/SEF-Group-25/discord-bot/tree/feat/1-cov-error-handler) shows the instrumented code.

### Evaluation

We use a function mark_branch(branch_id) to instrument. When the branch is reached, it will write branch id to a log file. Then we can deal with log file, count which branch ids do not appear and compute the coverage rate.

Our tool only supports branches that can be added a function call at the beginning. If without refactor of source code, the tool can't support branches like:
```python
# several conditions in if, we can't instrument for conditions seperately
if isinstance(e, errors.CommandNotFound) and not getattr(ctx, "invoked_from_error_handler", False):

# can't insert instrumentation in this line
filter_ for filter_ in self[ListType.ALLOW].filters.values() if await filter_.triggered_on(new_ctx)
```

After excluding special cases or refactoring code, the result of our tool is accurate, consistent with the result of `Coverage.py`.

## Coverage improvement

Requirements documentation for uncovered branches:

```python
if await self.try_run_fixed_codeblock(ctx):
    return  # if the command body is within triple backticks, then try to invoke it
    
except Exception as err:    # error raised by those three functions in try block
    
if isinstance(err, errors.CommandError):    
    # if the error is a CommandError, use on_command_error itself to handle it
    await self.on_command_error(ctx, err)
    
else:   # else it is a invoke error
    await self.on_command_error(ctx, errors.CommandInvokeError(err))
    
elif isinstance(e.original, Forbidden):
    # handle_forbidden_from_block() handles ``discord.Forbidden`` 90001 errors, 

except Forbidden:
    # re-handle the error if it isn't a 90001 error.
    await self.handle_unexpected_error(ctx, e.original)
```

Report of old coverage:
```bash
# Name                              Stmts   Miss Branch BrPart  Cover
bot/exts/backend/error_handler.py     245     68     96      7    73%
# Missing
25-29, 33-42, 47, 109, 111-116, 134-137, 162-163, 206-207, 212, 218-220, 236-257, 265-266, 268-288, 331-339
```

Report of new coverage:
```bash
# Name                              Stmts   Miss Branch BrPart  Cover
bot/exts/backend/error_handler.py     245     58     96      5    77%
# Missing
25-29, 33-42, 47, 165-166, 209-210, 215, 221-223, 239-260, 268-269, 271-291, 334-342
```

Test cases added:

git diff ...

## Self-assessment: Way of working

Current state according to the Essence standard: ...

Was the self-assessment unanimous? Any doubts about certain items?

How have you improved so far?

Where is potential for improvement?

## Overall experience

What are your main take-aways from this project? What did you learn?

Is there something special you want to mention here?
