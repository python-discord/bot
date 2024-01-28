---
embed:
    title: "Regular expressions"
---
Regular expressions (regex) are a tool for finding patterns in strings. The standard library's `re` module defines functions for using regex patterns.

**Example**
We can use regex to pull out all the numbers in a sentence:
```py
>>> import re
>>> text = "On Oct 18 1963 a cat was launched aboard rocket #47"
>>> regex_pattern = r"[0-9]{1,3}"  # Matches 1-3 digits
>>> re.findall(regex_pattern, text)
['18', '196', '3', '47']  # Notice the year is cut off
```
**See Also**
- [The re docs](https://docs.python.org/3/library/re.html) - for functions that use regex
- [regex101.com](https://regex101.com) - an interactive site for testing your regular expression
