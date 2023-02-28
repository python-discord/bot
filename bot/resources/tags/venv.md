---
aliases: ["virtualenv"]
embed:
    title: "Virtual environments"
---

Virtual environments are isolated Python environments, which make it easier to keep your system clean and manage dependencies. By default, when activated, only libraries and scripts installed in the virtual environment are accessible, preventing cross-project dependency conflicts, and allowing easy isolation of requirements.

To create a new virtual environment, you can use the standard library `venv` module: `python3 -m venv .venv` (replace `python3` with `python` or `py` on Windows)

Then, to activate the new virtual environment:

**Windows** (PowerShell): `.venv\Scripts\Activate.ps1`
or (Command Prompt): `.venv\Scripts\activate.bat`
**MacOS / Linux** (Bash): `source .venv/bin/activate`

Packages can then be installed to the virtual environment using `pip`, as normal.

For more information, take a read of the [documentation](https://docs.python.org/3/library/venv.html). If you run code through your editor, check its documentation on how to make it use your virtual environment. For example, see the [VSCode](https://code.visualstudio.com/docs/python/environments#_select-and-activate-an-environment) or [PyCharm](https://www.jetbrains.com/help/pycharm/creating-virtual-environment.html) docs.

Tools such as [poetry](https://python-poetry.org/docs/basic-usage/) and [pipenv](https://pipenv.pypa.io/en/latest/) can manage the creation of virtual environments as well as project dependencies, making packaging and installing your project easier.

**Note:** When using PowerShell in Windows, you may need to change the [execution policy](https://docs.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies) first. This is only required once per user:
```ps1
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
