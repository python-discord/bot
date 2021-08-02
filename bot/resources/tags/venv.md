**Virtual Environments**

Virtual environments are isolated Python environments, which make it easier to keep your system clean and manage dependencies. By default, when activated, only libraries and scripts installed in the virtual environment are accessible.

To create a new virtual environment, you can use the standard library `venv` module: `python3 -m venv .venv` (replace `python3` with `python` or `py` on windows)

Then, to activate the new virtual environment:

PowerShell: `.venv\Scripts\Activate.ps1`
Bash: `source .venv/bin/activate`

Note: On Windows, you may need to change the [execution policy](https://docs.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies) first:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Packages can then be installed to the virtual environment using `pip`, as normal.

For more information, take a read of the [documentation](https://docs.python.org/3/library/venv.html).
