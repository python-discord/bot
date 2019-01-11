# Contributing to one of our projects<sup>1</sup>

Our projects are open-source and are deployed as commits are pushed to the `master` branch on each repository, so we've created a set of guidelines in order to keep everything clean and in working order.

Note that contributions may be rejected on the basis of a contributor failing to follow these guidelines.

## Rules

1. **No force-pushes** or modifying the Git history in any way.
1. If you have direct access to the repository, **create a branch for your changes** and create a merge request for that branch. If not, create a branch on a fork of the repository and create a merge request from there.
    * It's common practice for a repository to reject direct pushes to `master`, so make branching a habit!
1. **Make great commits**<sup>2</sup>. A well structured git log is key to a project's maintainability; it efficiently provides insight into when and *why* things were done for future maintainers of the project.
    * Commits should be as narrow in scope as possible. Commits that span hundreds of lines across multiple unrelated functions and/or files are very hard for maintainers to follow. After about a week they'll probably be hard for you to follow too.
    * Commit messages should succintly *what* and *why* the changes were made.
    * Try to avoid making minor commits for fixing typos or linting errors. Since you've already set up a pre-commit hook to run `flake8` before a commit, you shouldn't be committing linting issues anyway.
1. **Avoid frequent pushes to the main repository**. Our test build pipelines are triggered every time a push to the repository is made. Where possible, try to batch your commits until you've finished working for that session, or collaborators need your commits to continue their work. This also provides you the opportunity to amend commits for minor changes rather than having to commit them on their own because you've already pushed.
1. If someone is working on a merge request, **do not open your own merge request for the same task**. Instead, collaborate with the author(s) of the existing merge request. Communication is key, and there's no point in two separate implementations of the same thing.
    * One option is to fork the other contributor's repository and submit your changes to their branch with your own merge request. We suggest following these guidelines when interacting with their repository as well.
1. **Adhere to the prevailing code style**, which we enforce using [flake8](http://flake8.pycqa.org/en/latest/index.html).
    * Run `flake8` against your code **before** you push it. Your commit will be rejected by the build server if it fails to lint.
    * [Git Hooks](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks) are a powerful tool that can be a daunting to set up. Fortunately, [`pre-commit`](https://github.com/pre-commit/pre-commit) abstracts this process away from you and is provided as a dev dependency for this project. Run `pipenv run precommit` when you set up the project and you'll never have to worry about breaking the build for linting errors.
1. **Don't fight the framework**. Every framework has its flaws, but the frameworks we've picked out have been carefully chosen for their particular merits. If you can avoid it, please resist reimplementing swathes of framework logic - the work has already been done for you!
1. **Work as a team** and collaborate whereever possible. Keep things friendly and help each other out - these are shared projects and nobody likes to have their feet trodden on.
1. **Internal projects are internal**. As a contributor, you have access to information that the rest of the server does not. With this trust comes responsibility - do not release any information you have learned as a result of your contributor position. We are very strict about announcing things at specific times, and many staff members will not appreciate a disruption of the announcement schedule.

Above all, the needs of our community should come before the wants of an individual. Work together, build solutions to problems and try to do so in a way that people can learn from easily. Abuse of our trust may result in the loss of your Contributor role, especially in relation to Rule 7.

## Changes to this arrangement

All projects evolve over time, and this contribution guide is no different. This document may also be subject to pull requests or changes by contributors, where you believe you have something valuable to add or change.

##  Supplemental Information
### Logging levels
The project currently defines [`logging`] levels as follows:
* **TRACE:** Use this for tracing every step of a complex process. That way we can see which step of the process failed. Err on the side of verbose.
* **INFO:** Something completely ordinary happened. Like a cog loading during startup.
* **DEBUG:** Someone is interacting with the application, and the application is behaving as expected.
* **WARNING:** Someone is interacting with the application in an unexpected way or the application is responding in an unexpected way, but without causing an error.
* **ERROR:** An error that affects the specific part that is being interacted with
* **CRITICAL:** An error that affects the whole application.

## Footnotes

1. This document was inspired by the [Glowstone contribution guidelines](https://github.com/GlowstoneMC/Glowstone/blob/dev/docs/CONTRIBUTING.md).
2. A more in-depth guide to writing great commit messages can be found in Chris Beam's [*How to Write a Git Commit Message*](https://chris.beams.io/posts/git-commit/)