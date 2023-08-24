---
embed:
    title: "Opening files"
---
The built-in function `open()` is one of several ways to open files on your computer. It accepts many different parameters, so this tag will only go over two of them (`file` and `mode`). For more extensive documentation on all these parameters, consult the [official documentation](https://docs.python.org/3/library/functions.html#open). The object returned from this function is a [file object or stream](https://docs.python.org/3/glossary.html#term-file-object), for which the full documentation can be found [here](https://docs.python.org/3/library/io.html#io.TextIOBase).

See also:  
- `!tags with` for information on context managers  
- `!tags pathlib` for an alternative way of opening files  
- `!tags seek` for information on changing your position in a file  

**The `file` parameter**

This should be a [path-like object](https://docs.python.org/3/glossary.html#term-path-like-object) denoting the name or path (absolute or relative) to the file you want to open.

An absolute path is the full path from your root directory to the file you want to open. Generally this is the option you should choose so it doesn't matter what directory you're in when you execute your module.

See `!tags relative-path` for more information on relative paths.

**The `mode` parameter**

This is an optional string that specifies the mode in which the file should be opened. There's not enough room to discuss them all, but listed below are some of the more confusing modes.

- `'r+'` Opens for reading and writing (file must already exist)
- `'w+'` Opens for reading and writing and truncates (can create files)
- `'x'` Creates file and opens for writing (file must **not** already exist)
- `'x+'` Creates file and opens for reading and writing (file must **not** already exist)
- `'a+'` Opens file for reading and writing at **end of file** (can create files)
