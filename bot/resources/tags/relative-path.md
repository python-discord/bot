---
embed:
    title: "Relative path"
---
A relative path is a partial path that is relative to your current working directory. A common misconception is that your current working directory is the location of the module you're executing, **but this is not the case**. Your current working directory is actually the **directory you were in when you ran the Python interpreter**. The reason for this misconception is because a common way to run your code is to navigate to the directory your module is stored, and run `python <module>.py`. Thus, in this case your current working directory will be the same as the location of the module. However, if we instead did `python path/to/<module>.py`, our current working directory would no longer be the same as the location of the module we're executing.

**Why is this important?**

When opening files in Python, relative paths won't always work since it's dependent on what directory you were in when you ran your code. A common issue people face is running their code in an IDE thinking they can open files that are in the same directory as their module, but the current working directory will be different than what they expect and so they won't find the file. The way to avoid this problem is by using absolute paths, which is the full path from your root directory to the file you want to open.
