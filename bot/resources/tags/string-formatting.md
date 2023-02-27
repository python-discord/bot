---
embed:
    title: "String formatting mini-language"
---
The String Formatting Language in Python is a powerful way to tailor the display of strings and other data structures. This string formatting mini language works for f-strings and `.format()`.

Take a look at some of these examples!
```py
>>> my_num = 2134234523
>>> print(f"{my_num:,}")
2,134,234,523

>>> my_smaller_num = -30.0532234
>>> print(f"{my_smaller_num:=09.2f}")
-00030.05

>>> my_str = "Center me!"
>>> print(f"{my_str:-^20}")
-----Center me!-----

>>> repr_str = "Spam \t Ham"
>>> print(f"{repr_str!r}")
'Spam \t Ham'
```
**Full Specification & Resources**
[String Formatting Mini Language Specification](https://docs.python.org/3/library/string.html#format-specification-mini-language)
[pyformat.info](https://pyformat.info/)
