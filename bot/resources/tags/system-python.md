---
embed:
    title: "System Python"
---

Unix-like systems such as Linux are equipped with a system Python interpreter intended for internal system operations. While it may be suitable for executing quick, one-off scripts, relying on it for development work can introduce a host of challenges and limitations.


**Why is it bad?**

• • Linux systems are very reliant on their system interpreter for a multitude of critical system operations, and it is essential for system functioning. Altering the interpreter and its dependencies may cause serious, irreversible harm to your system.

• For stability purposes, the interpreters are typically behind the current release by several versions, so you may not have access to the latest Python's features and security patches.

• Packages are typically externally-managed through your system's package manager, limiting your control over package versions and often confining you to outdated versions.

• The use of outdated packages can lead to compatibility issues when your project requirements don't align with the outdated package versions

**What should you use?**

To circumvent these issues, you can install another Python interpreter directly [from the source](https://www.python.org/downloads/), preferably within a virtual environment, allowing you to choose any interpreter you prefer.

Alternatively, you can use an [interpreter manager](https://github.com/pyenv/pyenv) like `Pyenv`. Pyenv enables you to manage multiple Python versions and create isolated development environments for different projects, ensuring a smooth and conflict-free development experience.

For an in-depth explanation about why it may not be in your best interest to use your system's interpreter, listen to this [enlightening audio](https://realpython.com/lessons/why-not-system-python/) by RealPython.
