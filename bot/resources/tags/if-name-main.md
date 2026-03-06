---
aliases: ["main"]
embed:
    title: '`if __name__ == "__main__"`'
---

This is a convention for code that should run if the file is the main file of your program:

```py
def main():
    ...

if __name__ == "__main__":
    main()
```

If the file is run directly, then the `main()` function will be run.
If the file is imported, it will not run.

For more about why you would do this and how it works, see
[`if __name__ == "__main__"`](https://pythondiscord.com/pages/guides/python-guides/if-name-main/).
