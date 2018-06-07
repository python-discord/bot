# Contributing to one of our projects

Our projects are open-source, and are deployed as commits are pushed to the `master` branch on each repository.
We've created a set of guidelines here in order to keep everything clean and in working order. Please note that
contributions may be rejected on the basis of a contributor failing to follow the guidelines.

## Rules

1. **No force-pushes** or modifying the Git history in any way.
1. If you have direct access to the repository, **create a branch for your changes** and create a merge request for that branch.
   If not, fork it and work on a separate branch there.
    * Some repositories require this and will reject any direct pushes to `master`. Make this a habit!
1. If someone is working on a merge request, **do not open your own merge request for the same task**. Instead, leave some comments
   on the existing merge request. Communication is key, and there's no point in two separate implementations of the same thing.
    * One option is to fork the other contributor's repository, and submit your changes to their branch with your 
      own merge request. If you do this, we suggest following these guidelines when interacting with their repository 
      as well.
1. **Adhere to the prevailing code style**, which we enforce using [flake8](http://flake8.pycqa.org/en/latest/index.html).
    * Additionally, run `flake8` against your code before you push it. Your commit will be rejected by the build server 
      if it fails to lint.
1. **Don't fight the framework**. Every framework has its flaws, but the frameworks we've picked out have been carefully 
    chosen for their particular merits. If you can avoid it, please resist reimplementing swathes of framework logic - the
    work has already been done for you!
1. **Work as a team** and cooperate where possible. Keep things friendly, and help each other out - these are shared
    projects, and nobody likes to have their feet trodden on.
1. **Internal projects are internal**. As a contributor, you have access to information that the rest of the server
    does not. With this trust comes responsibility - do not release any information you have learned as a result of
    your contributor position. We are very strict about announcing things at specific times, and many staff members
    will not appreciate a disruption of the announcement schedule.

Above all, the needs of our community should come before the wants of an individual. Work together, build solutions to
problems and try to do so in a way that people can learn from easily. Abuse of our trust may result in the loss of your Contributor role, especially in relation to Rule 7.

## Changes to this arrangement

All projects evolve over time, and this contribution guide is no different. This document may also be subject to pull 
requests or changes by contributors, where you believe you have something valuable to add or change.

## Footnotes

This document was inspired by the [Glowstone contribution guidelines](https://github.com/GlowstoneMC/Glowstone/blob/dev/docs/CONTRIBUTING.md).
