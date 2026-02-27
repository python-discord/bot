# Report for assignment 4

## Project

Name: Python Utility Bot

URL: [https://github.com/python-discord/bot](https://github.com/python-discord/bot)

A discord bot designed specifically for use with the [Python discord](https://www.pythondiscord.com/) server.
It is built with an extensible cog-based architecture, integrating numerous functionalities, such as moderation, community management, reminders, and many more.

## Onboarding experience

### Did you choose a new project or continue on the previous one?

We chose a new project, mainly as it was difficult to find an existing issue which would meet all the requirements set by the assignment.

### If you changed the project, how did your experience differ from before?

The project is much more complex than the one we chose for assignment 3, which became evident in the ammount of time needed with setting up the project environnment, and understanding the codebase.

### Setting up the project

The project setup was documented extremely well in the project's [Contributing guide](https://www.pythondiscord.com/pages/guides/pydis-guides/contributing/bot/).\
Installing the dependencies was straightforward using the `uv` package manager.
Most of the time was likely spent downloading and setting up Docker, particularly for those with no prior experience using it.

In addition to installing dependencies, the project required setting up both the test server and the actual bot and interconnecting them.
This process was also very well documented, and the project even provided a base template for the Discord server, resulting in a very quick setup.

The project documentation also explained how to run the tests, providing a README file containing all the necessary commands.
It included an introduction to writing new tests, along with a brief overview of how mocking is used, which provided some initial insight.

However, the documentation did not include an introduction to the actual codebase.
We spent a significant amount of time trying to understand how the project is structured and how different classes interact with one another.
Because the project is tightly integrated with Discord servers, this made it even more challenging, as some functions are triggered exclusively by the Discord API.
We believe that adding concrete examples or a high-level architectural diagram would be highly beneficial for newcomers.

## Effort spent

For each team member, how much time was spent in

1. plenary discussions/meetings;

2. discussions within parts of the group;

3. reading documentation;

4. configuration and setup;

5. analyzing code/output;

6. writing documentation;

7. writing code;

8. running code?

For setting up tools and libraries (step 4), enumerate all dependencies
you took care of and where you spent your time, if that time exceeds
30 minutes.

## Overview of issue(s) and work done.

Title: Handling of site connection issues during outage. (#2918)

URL: [https://github.com/python-discord/bot/issues/2918](https://github.com/python-discord/bot/issues/2918)

Since some cogs depend on external services (external sites), their initialization fails if those services are unavailable during startup, rendering their functionality inaccessible.
This failure occurs silently, without any indication to moderators.

Scope (functionality and code affected).

**Functionality affected**
- Startup behavior of cogs depending on external HTTP services.
- Error handling, error propagation.
- Retry logic with back-off.
- Logging and allerting of moderators.

**Code affected**
- `cog_load()` implementations in affected cogs.
- Sentry reporting during individual retries and final error.
- Discord message API interaction to alert moderators.
- Associated unit tests covering cog initialization.
- Extension loading failure handling in `bot.py`
## Requirements for the new feature or requirements affected by functionality being refactored

Optional (point 3): trace tests to requirements.

## Code changes

### Patch

(copy your changes or the add git command to show them)

git diff ...

Optional (point 4): the patch is clean.

Optional (point 5): considered for acceptance (passes all automated checks).

## Test results

Overall results with link to a copy or excerpt of the logs (before/after
refactoring).

## UML class diagram and its description

### Key changes/classes affected

Optional (point 1): Architectural overview.

Optional (point 2): relation to design pattern(s).

## Overall experience

What are your main take-aways from this project? What did you learn?

How did you grow as a team, using the Essence standard to evaluate yourself?

Optional (point 6): How would you put your work in context with best software engineering practice?

Optional (point 7): Is there something special you want to mention here?
