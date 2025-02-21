# Report for assignment 3

## Project

Name: `python-discord/bot`

URL: https://github.com/python-discord/bot/tree/main

It is a Discord bot specifically for use with the Python Discord server which has ~400k members. It provides numerous utilities and other tools to help keep the server running like a well-oiled machine.

## Onboarding experience

It mostly ran flawlessly, with a few caveats as outlined below:
- @strengthless was on Apple Silicon M2 chip, and some docker images were not pulled successfully on the first try.
  - I had to refer to [this stack overflow article](https://stackoverflow.com/questions/65456814/docker-apple-silicon-m1-preview-mysql-no-matching-manifest-for-linux-arm64-v8) and run the command `export DOCKER_DEFAULT_PLATFORM=linux/x86_64/v8`
- @strengthless kept getting the `PrivilegedIntentsRequired` error upon docker startup.
  - Turns out when setting up [Privileged Gateway Intents](https://www.pythondiscord.com/pages/guides/pydis-guides/contributing/bot/#privileged-intents), aside from `Server Member Intent`, you also need to enable `Message Content Intent`, which is a relatively new intent introduced by Discord.
  - We have submitted a PR in [python-discord/site](https://github.com/python-discord/site/pull/1470) for updating the relevant documentations, which has been accepted.

After setting up the environment, we ran a quick analysis on LoCs and test coverage:
```bash
# lines of code in python (~19.3k)
cloc ./bot
# branch coverage (~50%)
poetry run task test-cov && poetry run task report
```

With everything combined, we deemed the project suitable for this assignment.

## Complexity

1. What are your results for five complex functions?
    * Did all methods (tools vs. manual count) get the same result?
        - Using [lizard](https://pypi.org/project/lizard/) (`lizard --sort nloc`), we found those five large functions:
          ```
            NLOC    CCN   token  PARAM  length  location  
          ------------------------------------------------
            141     26    652      8     175 apply_infraction@126-300@./bot/exts/moderation/infraction/_scheduler.py
            114     17    577      5     140 deactivate_infraction@393-532@./bot/exts/moderation/infraction/_scheduler.py
            108     18    485      5     130 infraction_edit@149-278@./bot/exts/moderation/infraction/management.py
            101     16    304      5     113 humanize_delta@131-243@./bot/utils/time.py
             76     20    412      3      85 on_command_error@65-149@./bot/exts/backend/error_handler.py
          ```
        - By counting manually and cross-checking, we reached the following consensus:
            - For `apply_infraction@infraction/_scheduler.py`, we get 27 CCN.
            - For `deactivate_infraction@infraction/_scheduler.py`, we get 17 CCN.
            - For `infraction_edit@infraction/management.py`, we get 18 CCN.
            - For `humanize_delta@utils/time.py`, we get 16 CCN.
            - For `on_command_error@backend/error_handler.py`, we get 20 CCN.
    * Are the results clear?
        - Some of us got different results. Upon discussing further, it was discovered that we had different methods in counting CCNs, e.g. how we deal with switch-cases, logical operators, list comprehensions, etc. Once we had those clarified, we started getting consistent results.
        - The CCNs we counted were mostly the same as Lizard's. There is, however, one small caveat for `apply_infraction@infraction/_scheduler.py` - we counted 27 CCN instead of 26.
            - Upon further investigation, it looks like line 299 was not counted by Lizard, which included a ternary operator within a string literal.
2. Are the functions just complex, or also long?
    - We observe a slight correlation, but no causal effects. Generally speaking, if a function is long, then it's more probable that it contains some sort of complex code. However, there is no strict correlation here, as short functions can still be complex, vice versa.
3. What is the purpose of the functions?
    - For `deactivate_infraction@infraction/_scheduler.py`, it is a function that deactivates infraction status for users in the database and returns a log of the removed infraction.
    - For `apply_infraction@infraction/_scheduler.py`, it is a function that applies an infraction to the user and logs the infraction. It can also notify the user of the infraction.
    - For `infraction_edit@infraction/management.py` modifies punishments for users who have violated server rules and notifies moderators about the changes. It is used by `infraction_append`, which applies new punishments, since the two functions share most logic. The function must handle various edge cases, such as preventing edits to expired infractions or warnings. It also processes multiple input formats and validates the request before making API calls. These requirements introduce multiple decision points, contributing to its high CC.
    - For `humanize_delta@utils/time.py`, it is a function that takes in a period of time (e.g. start and end timestamps) as its arguments, then convert it into a human-readable string.
    - For `on_command_error@./bot/exts/backend/error_handler.py`, it is a function that provides error messages given a generic error by deferring errors to local error handlers.
4. Are exceptions taken into account in the given measurements?
    - Yes, for both Lizard and our manual counting. If we don't take them into account, then the resultant CCN could drop.
5. Is the documentation clear w.r.t. all the possible outcomes?
    - For `deactivate_infraction@infraction/_scheduler.py`, some parts of the function were easy to read with regards to all the possible outcomes, as the function utilises if/else statements in variable assignment without documenting the use case.
    - For `apply_infraction@infraction/_scheduler.py`, the function is quite easy to read and understand by the given documentation.
    - For `infraction_edit@infraction/management.py` was fairly well-documented with many branches having comments describing the consequences or reasons for the branch. Additionally, it includes logging strings that serve both as messages and as documentation further describing outcomes.The documentation is overall very clear and not overstated as Python’s readability allows much to be inferred directly from the clauses.
    - For `humanize_delta@utils/time.py`, exceptions were not explicitly documented. Other than that, the function only produces a string as its outcome, therefore we think the documentation was mostly clear.
    - For `on_command_error@./bot/exts/backend/error_handler.py`, the documentation provides a clear and concise description of most of the functions behaviour, but seems to fail to document the `CommandInvokeError` branch behaviour almost entirely.

## Refactoring

Plan for refactoring complex code:
- For `apply_infraction@infraction/_scheduler.py`, we can extract most of the code related to logging of the results. This code be handled in a seperate function. This would reduce the amount of CCN significantly.
- For `deactivate_infraction@infraction/_scheduler.py`, we plan on extracting the 3 different try/exepct blocks into separate methods (pardon_infraction, user_is_watched, update_db).
- For `humanize_delta@utils/time.py`, we plan on extracting methods, as the function is composed of two main parts, parsing of overload arguments into time delta, and stringification of the delta. Arguably, the former can be delegated to a separate helper function, which should greatly reduce the cyclomatic complexity.  
- For `actions_for@./bot/exts/filtering/_filter_lists/invite.py`, we plan on extracting methods, as the function is composed of many steps that can be isolated into separate functions. One could extract functionalities like redefining invites, sorting invites, finding blocked invites and cleaning up invites into separate functions.  
- For `infraction_edit@infraction/management.py`, despite all code being relevant, we can still make changes to the complexity by refactoring and dividing the function into less complex functions which can be used by other functions in the future. More specifically, we can separate the rescheduling functionality from infraction_edit making a helper function which reschedules an infraction when necessary.

Estimated impact of refactoring (lower CC, but other drawbacks?):
- For `apply_infraction@infraction/_scheduler.py`, no particular drawbacks should arise. It should decrease the CC with about 40%.
- For `deactivate_infraction@infraction/_scheduler.py`, some drawbacks are decreased readablility of the code and increased function calls.
- For `humanize_delta@utils/time.py`, no drawbacks are anticipated, except for the use of `typing.Any` in the type signature for the new helper function. However, since type hints are not strongly enforced in Python (they're just **hints** for humans), this should not be a huge deal.  
- For `actions_for@./bot/exts/filtering/_filter_lists/invite.py`, no drawbacks are anticipated.
- For `infraction_edit@infraction/management.py`, it should decrease the CC from 18 to 11, which is a decrease of about 39%. No drawbacks are anticipated.

Carried out refactoring (optional, P+):
- For `humanize_delta@utils/time.py`, we have [PR #4](https://github.com/dd2480-spring-2025-group-1/bot/pull/4) which reduces CCN by 37.5%.
- For `actions_for@./bot/exts/filtering/_filter_lists/invite.py`, we have [PR #22](https://github.com/dd2480-spring-2025-group-1/bot/pull/22) which reduces CCN by 35.1%.
- For `infraction_edit@infraction/management.py`, we have [PR #21](https://github.com/dd2480-spring-2025-group-1/bot/pull/21) which reduces CCN by about 39%.

Note: since `on_command_error@error_handler.py` already has 100% test coverage as reported by `coverage.py`, we decided to do part 2 of the assignment with `actions_for@invite.py` instead, which is the function with the highest CCN as reported by lizard (CCN 37) and it has 20% test coverage.

## Coverage

### Tools

We used [coverage.py](https://coverage.readthedocs.io/en/7.6.12/) as our main coverage tool, as the tool had already been integrated into the project.

The tool's usage had been well documented in `tests/README.md`, with shortcut commands implemented.

There is only one small caveat here: coverage by function or class is not natively supported by `coverage.py` in the CLI (see this [github issue](https://github.com/nedbat/coveragepy/issues/1859) for more information). We specifically switched to a fork version of `coverage.py` for this.
- To view the branch coverage report for a specific function, you can now run `poetry run task report --functions` with the help of the fork.
- To view the missing branches, there is still no easy method. You need to add `# pragma: no cover` to ignore all other functions in the file, then export a JSON report via `poetry run coverage json ./path/to/somefile.py`.

### Your own coverage tool

Show a patch (or link to a branch) that shows the instrumented code to
gather coverage measurements:
- For `humanize_delta@utils/time.py`, we have [PR #10](https://github.com/dd2480-spring-2025-group-1/bot/pull/10)
- For `infraction_edit@infraction/management.py`: we have [PR #28](https://github.com/dd2480-spring-2025-group-1/bot/pull/28). This PR includes created tests from later in the assignment since the coverage tool will otherwise not run if there are no tests as described in the limitations of the tool.

What kinds of constructs does your tool support, and how accurate is
its output?
- We provide a general framework for manually appending the instrumentations:
    - For boolean related constructs (e.g., `if`, `elif`, `x if y else z`, `while`, etc.), wrap the boolean with `cov_if(bool, idx, idx+1)`.
    - For loop related constructs (e.g., `for`, `x for y in z`, etc.), wrap the iterable with `cov_for(list, idx, idx+1)`.
    - We currently do not support switch cases, generators, or other constructs that were not explicitly mentioned above.
    - You can then run `poetry run task test -rP -n 1 ./path/to/somefile.py` to run the test cases and view its coverage report.
- The reporting tool should be accurate (assuming that all required constructs are supported), though it is highly prone to human errors, as it requires manual analysis on the branches for setting up the coverage tool.

### Evaluation

1. How detailed is your coverage measurement?
- We report the overall coverage of a function, and the IDs of the branches that were not covered.
- The level of "detailness" depends on the person implementing the coverage - whether they decide to include coverage for boolean operators (i.e., `and`, `or`), exceptions, or list comprehensions etc.

2. What are the limitations of your own tool?
- As mentioned above, there are some constructs that we currently do not support.
- It requires manual analysis on the branching of the code.
- Once set up, the readability of the code is greatly affected, as a lot of `cov_if` and `cov_for` function calls are injected into the original code, which causes some degree of "obfuscation".
- Another limitation is that there will be no coverage output if no tests exist for the function since the coverage tool will never be run.

3. Are the results of your tool consistent with existing coverage tools?
- The reported number of total branches are consistent.
- However, the numbers of missing branches (which you can obtain using `poetry run coverage json ./bot/utils/time.py`) are different.
    - Upon further investigation, we realized that it's because our tool was only checking against `test_time.py` for branch coverage on `time.py`. On the contrary, `coverage.py` records all LoC transitions when running **all** test files, then compares them against a list of possible branch transitions (statically analysed), which yields the final branch coverage report ([ref](https://coverage.readthedocs.io/en/7.6.12/branch.html#how-it-works)).
    - For example, let's assume `humanize_delta@time.py` is used in the function `get_slowmode@slowmode.py`, and `get_slowmode` is tested in `test_slowmode.py`. When the test suite for `test_slowmode.py` runs, some branches within `humanize_delta@time.py` will also be executed, and thereby increasing the branch coverage on `time.py`, despite it not being tested directly.
    - This explains why `coverage.py` reports higher coverage than our tool, though we would argue that no tool is in the wrong here - it's just a matter of perspective, whether you prefer to infer coverage from only the "direct" test cases, or also the "indirect" ones.
        - In fact, we might even suggest that our tool is better in this case, as the indirect ones are much harder to debug if there happens to be a regression, because it's now some random test `test_slowmode.py` failing, instead of the actual culprit `humanize_delta@time.py`, which would've been reported if there were 100% "direct coverage".

## Coverage improvement

Show the comments that describe the requirements for the coverage:
- For `utils/helpers.py`, the functions are fairly straightforward. The requirements were already well documented in the one-line docstrings. The only caveat here is the `has_lines` function, which ignores one `\n` character from the end of the string when counting the number of lines.
- For `infraction_edit@infraction/management.py`, there were no tests before but the documentation of the function was clear and helped in creating the requirements, e.g.:
    - The function should raise a BadArgument when a duration and a reason is not provided.
    - The function should not allow editing the duration of a warning or note infraction.
    - The function should not allow editing the duration of an expired infraction.
    - The function should call the `api_client.patch` method to update an infraction when a new reason is provided.
- For `apply_fpr@./bot/exts/filtering/_filter_lists/invite.py` there were no tests before. The function documentation is very scarce, thus the test cases had to be derived from the code itself. Some parts of the code are inaccessible since they require certain filters to trigger, which is not realizable with the MockBot used which generates random ids and data.
Nonetheless the following tests could be implemented:
  - The function should return success for a valid invite url, i.e. empty action, a message containing the invite code and the list filter that allowed the invite (since no filter triggered it, it should be ListType.ALLOW:[]).
  - The function should return failure when there is no invite url in the ctx content, i.e. it should return None as action, an empty message and an empty dictionary for the list type.
  - The function should return failure when the invite url is invalid.
  - The function should return success for a different but valid url.

Report of old coverage:
```
Name                                          Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------------------------
bot/utils/helpers.py                            23      8      4      1    67%   19, 25-28, 38-43
infraction_edit@management.py                   51     51     26      0     0%   192-281
bot/exts/filtering/_filter_lists/invite.py      93     69     32      1    20%   19, 47-48, 52, 57, 63-152, 157-172
```

Report of new coverage:
```
Name                                          Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------------------------
bot/utils/helpers.py                            23      0      4      0   100%
infraction_edit@management.py                   51     22     26      7    52%   188, 194-195, 197-202, 214, 229-242, 254-255, 261
bot/exts/filtering/_filter_lists/invite.py      93     13     32     10    77%   19, 57, 76->78, 90-92, 96-97, 117->128, 129, 132->135, 136-140, 145->148, 161->166, 164


```

Test cases added:
- For `utils/helpers.py`, [PR #3260](https://github.com/python-discord/bot/pull/3260) had been created by @strengthless, approved and merged into the upstream, which included 7 new test cases.
- For `infraction_edit@infraction/management.py`, [PR #38](https://github.com/dd2480-spring-2025-group-1/bot/pull/38) has been drafted.
- For `apply_fpr@./bot/exts/filtering/_filter_lists/invite.py`, [PR #44](https://github.com/dd2480-spring-2025-group-1/bot/pull/44) has been drafted.

## Self-assessment: Way of working

We would now argue that we have reached the “In Place” state. We previously estimated that we were close to reaching “In Place” but had to work more as a group on modifying and improving the practices in the group. For this project all group members have participated in trying to modify and improve the Ways of Working.

To reach the next state “Working Well” we would need to work on becoming more comfortable with the practices, in order to apply them naturally without thinking about them. Additionally we would need to improve the “continually tunes their use of the practices and tools."

## Overall experience

What are your main take-aways from this project? What did you learn?
One takeaway from this project is that GitHub automatically wants to make pull requests towards the main repository and not the fork. This caused us to bloat the main repository with faulty PRs. More importantly, we learned about function coverage and how to calculate it, helping us write better test cases. The hardest thing to learn was how to implement our own tests in a project built by someone else, many struggled with seemingly random errors that required them to thoroughly read the code and learn how it works. This lesson will be useful for all of us when we contribute to other projects in the future.

As an additional note for P+, we have a working patch ([PR #3260](https://github.com/python-discord/bot/pull/3260)) accepted and merged into the upstream, which included a small fix along with the addition of 7 new test cases. The persons who are aiming for P+ are Johan (@joel90688), Kim (@strengthless) and Marcello (@Celleforst)
