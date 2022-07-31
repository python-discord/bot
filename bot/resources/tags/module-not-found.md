**module-not-found**

A `ModuleNotFoundError` is raised when the python interpreter cannot find a `module` either in the local directory or in the `site-packages` directory.

If you are expecting to use an `external` module, ie one that is *not* built-in (also know as `std` for `standard`) but cannot figure out why `ModuleNotFoundError` is raised, two things may be happening.

**Either, you have not used the python package manager, `pip`, to install the `library` (see below) in which case you need to:**

> First you need to open up the *command prompt*. *Note* that this is *not* the python interpreter.
>
> Then, you need to install the library with `pip` in order to add it to use it globally.
>
> ```
> pip install <library name>
> ```
>
> This then installs the library so that you can `import` it in your program.

**Or, you have multiple python interpreters installed, causing conflicts with the packages.**

In which case, see `!tags multiple-python`


> *Note*
>
> There is often the mention of the word `library`. A `library` is a *collection* of `modules`.

See `!tags module` for more information about what a `module` is.
