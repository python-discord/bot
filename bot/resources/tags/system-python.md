---
embed:
    title: "System Python"
---

*Why Avoid System Python for Development on Unix-like Systems:*

- **Critical System Operations Dependency:** Altering the system interpreter may harm system functioning irreversibly.
  
- **Stability and Security Concerns:** System interpreters lag behind current releases, lacking the latest features and security patches.
  
- **Limited Package Control:** External package management restricts control over versions, leading to compatibility issues with outdated packages.

*Recommended Approach:*

- **Install Independent Interpreter:** Install Python from source or utilize a virtual environment for flexibility and control.

- **Utilize Pyenv or Similar Tools:** Manage multiple Python versions and create isolated development environments for smoother workflows.
