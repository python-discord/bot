---
aliases: ["slice", "seqslice", "seqslicing", "sequence-slice", "sequence-slicing"]
embed:
    title: "Sequence slicing"
---
**Slicing** is a way of accessing a part of a sequence by specifying a start, stop, and step. As with normal indexing, negative numbers can be used to count backwards.

**Examples**
```py
>>> letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
>>> letters[2:]  # from element 2 to the end
['c', 'd', 'e', 'f', 'g']
>>> letters[:4]  # up to element 4
['a', 'b', 'c', 'd']
>>> letters[3:5]  # elements 3 and 4 -- the right bound is not included
['d', 'e']
>>> letters[2:-1:2]  # Every other element between 2 and the last
['c', 'e']
>>> letters[::-1]  # The whole list in reverse
['g', 'f', 'e', 'd', 'c', 'b', 'a']
>>> words = "Hello world!"
>>> words[2:7]  # Strings are also sequences
"llo w"
```
