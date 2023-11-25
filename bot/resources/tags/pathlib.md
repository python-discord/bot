---
embed:
    title: "The `pathlib` module"
---
Python 3 comes with a new module named `Pathlib`. Since Python 3.6, `pathlib.Path` objects work nearly everywhere that `os.path` can be used, meaning you can integrate your new code directly into legacy code without having to rewrite anything. Pathlib makes working with paths way simpler than `os.path` does.

**Feature spotlight**:

- Normalizes file paths for all platforms automatically  
- Has glob-like utilites (eg. `Path.glob`, `Path.rglob`) for searching files  
- Can read and write files, and close them automatically  
- Convenient syntax, utilising the `/` operator (e.g. `Path('~') / 'Documents'`)  
- Can easily pick out components of a path (eg. name, parent, stem, suffix, anchor)  
- Supports method chaining  
- Move and delete files  
- And much more  

**More Info**:

- [**Why you should use pathlib** - Trey Hunner](https://treyhunner.com/2018/12/why-you-should-be-using-pathlib/)  
- [**Answering concerns about pathlib** - Trey Hunner](https://treyhunner.com/2019/01/no-really-pathlib-is-great/)  
- [**Official Documentation**](https://docs.python.org/3/library/pathlib.html)  
- [**PEP 519** - Adding a file system path protocol](https://peps.python.org/pep-0519/)
