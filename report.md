# Report for assignment 4

## Project

Name: Discord bot

URL: https://github.com/python-discord/bot

This project is a Discord bot specifically for use with the Python Discord server. It provides numerous utilities and other tools to help keep the server running like a well-oiled machine.

## Onboarding experience

We continue on the previous project, the onboarding experience can be found in the [report for assignment 3](https://github.com/SEF-Group-25/discord-bot/blob/main/report.md)

## Effort spent

plenary discussions/meetings;
- a meeting to decide the issue, 1h
- a discussion over the plan to solve the issue, 2h
- a meeting to decide the division of work, 1h

discussions within parts of the group;
- voice call to confirm technical details, 1h
- text discussion, 1h

reading documentation;
- search and read documentation and manual, 3h

configuration and setup;
- set up and run the bot using docker, 1h

analyzing code/output;
- analyze the source code structure, 2h
- analyze the feature and utility functions we need to use, 2h

writing documentation;
- write the report, 2h
- draw diagrams, 2h

writing code;
- write the feature code, 2h
- write test cases, 1h

running code?
- running the bot and test cases, 2h

## Overview of issue(s) and work done.

Title: Keyword Alerts

URL: https://github.com/python-discord/bot/issues/3153

Send a DM to members when the bot detects a certain keyword in the incoming messages. And also be careful of malicious trigger of the detector (DDoS attack).

To fix this issue, a new command will be added to the bot. It is a new feature so it won't affect other functionalities of the discord bot.

## Requirements for the new feature or requirements affected by functionality being refactored

### Requirement: Spam Check #6

Title: Rate Limiting System for Preventing Malicious Trigger Abuse

Description:
This system implements a rate limiter to prevent users from excessively triggering a specific action (e.g., sending a DM) within a short time frame. It tracks message triggers per user and enforces a threshold-based restriction within a defined time window. If a user exceeds the allowed trigger count, they are flagged as malicious.

Test cases: test_spam_check.py

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

### Architectural overview

### relation to design patterns

The newly added command follows three key design patterns: Command Pattern, Observer Pattern, and Decorator Pattern. These patterns contribute to a modular, maintainable, and scalable architecture for the bot's functionality.

#### Command Pattern
The bot’s command system is structured using the Command Pattern, where each command is encapsulated as an independent function inside a `commands.Cog` subclass. By using this pattern, the bot's command system becomes more scalable since new commands can be added simply by creating new Cog classes without modifying the existing system.

#### Observer Pattern
The bot’s event-driven system follows the Observer Pattern, where multiple event listeners can be registered dynamically and notified when an event occurs. The `Cog` class registers event listeners, allowing them to subscribe to specific Discord events, such as `on_message`. The bot acts as the subject (publisher), and the Cog modules function as observers (subscribers). When an event (e.g., a message being sent) occurs, all registered observers are notified and can execute their logic.

#### Decorator Pattern
The command system uses the Decorator Pattern to define and register both commands and event listeners. The `@commands.command()` decorator automatically registers a method as a bot command without requiring manual intervention. The `@commands.Cog.listener()` decorator transforms a method into an event handler, making it a part of the bot’s event-driven system. Instead of manually mapping function names to commands or events, decorators enhance readability by explicitly marking functions as commands or listeners.

## Overall experience

From this project, I learned how to work as a group to solve code issues. We discussed the direction of solving the problem and developed a plan in detail. This is a valuable practical experience.

How did you grow as a team, using the Essence standard to evaluate yourself?

Optional (point 6): How would you put your work in context with best software engineering practice?

Optional (point 7): Is there something special you want to mention here?
