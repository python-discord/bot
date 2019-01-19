# Contributing to one of our projects

Our projects are open-source and are automatically deployed whenever commits are pushed to the `master` branch on each repository, so we've created a set of guidelines in order to keep everything clean and in working order.

Note that contributions may be rejected on the basis of a contributor failing to follow these guidelines.

## Rules

1. **No force-pushes** or modifying the Git history in any way.
2. If you have direct access to the repository, **create a branch for your changes** and create a pull request for that branch. If not, create a branch on a fork of the repository and create a pull request from there.
    * It's common practice for a repository to reject direct pushes to `master`, so make branching a habit!
3. **Adhere to the prevailing code style**, which we enforce using [flake8](http://flake8.pycqa.org/en/latest/index.html).
    * Run `flake8` against your code **before** you push it. Your commit will be rejected by the build server if it fails to lint.
    * [Git Hooks](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks) are a powerful tool that can be a daunting to set up. Fortunately, [`pre-commit`](https://github.com/pre-commit/pre-commit) abstracts this process away from you and is provided as a dev dependency for this project. Run `pipenv run precommit` when setting up the project and you'll never have to worry about breaking the build for linting errors.
4. **Make great commits**. A well structured git log is key to a project's maintainability; it efficiently provides insight into when and *why* things were done for future maintainers of the project.
    * Commits should be as narrow in scope as possible. Commits that span hundreds of lines across multiple unrelated functions and/or files are very hard for maintainers to follow. After about a week they'll probably be hard for you to follow too.
    * Try to avoid making minor commits for fixing typos or linting errors. Since you've already set up a pre-commit hook to run `flake8` before a commit, you shouldn't be committing linting issues anyway.
    * A more in-depth guide to writing great commit messages can be found in Chris Beam's [*How to Write a Git Commit Message*](https://chris.beams.io/posts/git-commit/)
5. **Avoid frequent pushes to the main repository**. This goes for PRs opened against your fork as well. Our test build pipelines are triggered every time a push to the repository (or PR) is made. Try to batch your commits until you've finished working for that session, or you've reached a point where collaborators need your commits to continue their own work. This also provides you the opportunity to amend commits for minor changes rather than having to commit them on their own because you've already pushed.
    * This includes merging master into your branch. Try to leave merging from master for after your PR passes review; a maintainer will bring your PR up to date before merging. Exceptions to this include: resolving merge conflicts, needing something that was pushed to master for your branch, or something was pushed to master that could potentionally affect the functionality of what you're writing.
6. **Don't fight the framework**. Every framework has its flaws, but the frameworks we've picked out have been carefully chosen for their particular merits. If you can avoid it, please resist reimplementing swathes of framework logic - the work has already been done for you!
7. If someone is working on a pull request, **do not open your own pull request for the same task**. Instead, collaborate with the author(s) of the existing pull request. Communication is key, and there's no point in two separate implementations of the same thing.
    * One option is to fork the other contributor's repository and submit your changes to their branch with your own pull request. We suggest following these guidelines when interacting with their repository as well.
8. **Work as a team** and collaborate whereever possible. Keep things friendly and help each other out - these are shared projects and nobody likes to have their feet trodden on.
9. **Internal projects are internal**. As a contributor, you have access to information that the rest of the server does not. With this trust comes responsibility - do not release any information you have learned as a result of your contributor position. We are very strict about announcing things at specific times, and many staff members will not appreciate a disruption of the announcement schedule.

Above all, the needs of our community should come before the wants of an individual. Work together, build solutions to problems and try to do so in a way that people can learn from easily. Abuse of our trust may result in the loss of your Contributor role, especially in relation to Rule 7.

## Changes to this arrangement

All projects evolve over time, and this contribution guide is no different. This document is open to pull requests or changes by contributors. If you believe you have something valuable to add or change, please don't hesitate to do so in a PR.

##  Supplemental Information
### Developer Environment
A working environment for the [PyDis site](https://github.com/python-discord/site) is required to develop the bot. Instructions for setting up environments for both the site and the bot can be found on the PyDis Wiki:
  * [Site](https://wiki.pythondiscord.com/wiki/contributing/project/site)
  * [Bot](https://wiki.pythondiscord.com/wiki/contributing/project/bot)

### Logging levels
The project currently defines [`logging`](https://docs.python.org/3/library/logging.html) levels as follows:
* **TRACE:** Use this for tracing every step of a complex process. That way we can see which step of the process failed. Err on the side of verbose. **Note:** This is a PyDis-implemented logging level.
* **DEBUG:** Someone is interacting with the application, and the application is behaving as expected.
* **INFO:** Something completely ordinary happened. Like a cog loading during startup.
* **WARNING:** Someone is interacting with the application in an unexpected way or the application is responding in an unexpected way, but without causing an error.
* **ERROR:** An error that affects the specific part that is being interacted with
* **CRITICAL:** An error that affects the whole application.

## Footnotes

This document was inspired by the [Glowstone contribution guidelines](https://github.com/GlowstoneMC/Glowstone/blob/dev/docs/CONTRIBUTING.md).
