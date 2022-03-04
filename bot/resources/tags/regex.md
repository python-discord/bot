**Regular expressions**
Sometimes you might want to detect a certain pattern of characters in a string without looking for every possible substring. Regular expressions (regex) are a language for specifying patterns that is used in many programming languages. Python's standard library includes the `re` module, which defines functions for using regex patterns.

**Example**
We can use regex to pull out all the numbers in a sentence:
```py
>>> import re
>>> x = "On Oct 18, 1963 Félicette the cat was launched into space aboard Veronique AGI sounding rocket No. 47."
>>> pattern = r"[0-9]{1,3}"  # Matches one to three digits
>>> re.findall(pattern,  x)
['18', '196', '3', '47']     # Notice the year got cut off
```
**See Also**
• [The re docs](https://docs.python.org/3/library/re.html) for more about the syntax and the functions that use regex
• [regex101.com](https://regex101.com) - a great site for experimenting with regular expressions