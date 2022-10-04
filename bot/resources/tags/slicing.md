---
aliases: ["slice", "seqslice", "seqslicing", "sequence-slice", "sequence-slicing"]
embed:
    title: "Sequence slicing"
---
You're trying to get a part of a string, list, or another sequence object, but you don't want to manually increment and concatenate? There comes the need to *slice* it.

There is a special syntax that can be used to slice a given `some_seq` sequence: `some_seq[i:j:k]`, where `i` is the starting index, `j` is the end index, and `k` is the step, i.e. every how many items should one be kept (the first one is always kept). `i`, `j`, and `k` all must be integers. If any of these values are missing, they're assumed as `some_seq[0:len(some_seq):1]`.

To slice something, the brackets must have at least at least a colon (cannot be empty). Using just `[:]` or `[::]` (without any numbers) will return a *copy* of the iterable if it's a `list` or a `bytearray`, reducing the need for the `copy()` method.

**Examples**
```py
>>> l = [1, 2, 3, 4]
>>> l[2:]
[3, 4]
>>> l[:2]
[1, 2]
>>> l[::-1]
[4, 3, 2, 1]
>>> l[:]
[1, 2, 3, 4]
>>> l[::2]
[1, 3]
```
Using `some_list[::-1]` is the same as `list(reversed(some_list))`. Just like in regular sequence subscriptions, negative integers may be used.

**Notes**
• If the start index is greater than the end index, the resulting sequence will be empty.
• The number of items before applying the step can be calculated as `n = j - i`.
• The number of items after applying the step is `n / k`, rounded down, but cannot be less than 1, unless `n` is exactly 0.
