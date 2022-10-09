---
aliases: ["minusmpip"]
embed:
    title: "Install packages with `python -m pip`"
---
When trying to install a package via `pip`, it's recommended to invoke pip as a module: `python -m pip install your_package`.

**Why would we use `python -m pip` instead of `pip`?**
Invoking pip as a module ensures you know *which* pip you're using. This is helpful if you have multiple Python versions. You always know which Python version you're installing packages to.

**Note**
The exact `python` command you invoke can vary. It may be `python3` or `py`, ensure it's correct for your system.
