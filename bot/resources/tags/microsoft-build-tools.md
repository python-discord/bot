---
embed:
    title: "Microsoft Visual C++ Build Tools"
---
When you install a library through `pip` on Windows, sometimes you may encounter this error:

```
error: Microsoft Visual C++ 14.0 or greater is required. Get it with "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

This means the library you're installing has code written in other languages and needs additional tools to install. To install these tools, follow the following steps: (Requires 6GB+ disk space)

**1.** Open [https://visualstudio.microsoft.com/visual-cpp-build-tools/](https://visualstudio.microsoft.com/visual-cpp-build-tools/).
**2.** Click **`Download Build Tools >`**. A file named `vs_BuildTools` or `vs_BuildTools.exe` should start downloading. If no downloads start after a few seconds, click **`click here to retry`**.
**3.** Run the downloaded file. Click **`Continue`** to proceed.
**4.** Choose **C++ build tools** and press **`Install`**. You may need a reboot after the installation.
**5.** Try installing the library via `pip` again.
