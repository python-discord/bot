---
embed:
    title: "Round half to even*"
---
Python 3 uses bankers' rounding (also known by other names), where if the fractional part of a number is `.5`, it's rounded to the nearest **even** result instead of away from zero.

Example:
```py
>>> round(2.5)
2
>>> round(1.5)
2
```
In the first example, there is a tie between 2 and 3, and since 3 is odd and 2 is even, the result is 2.
In the second example, the tie is between 1 and 2, and so 2 is also the result.

**Why this is done:**
The round half up technique creates a slight bias towards the larger number. With a large amount of calculations, this can be significant. The round half to even technique eliminates this bias.

It should be noted that round half to even distorts the distribution by increasing the probability of evens relative to odds, however this is considered less important than the bias explained above.

**References:**  
- [Wikipedia article about rounding](https://en.wikipedia.org/wiki/Rounding#Round_half_to_even)  
- [Documentation on `round` function](https://docs.python.org/3/library/functions.html#round)  
- [`round` in what's new in python 3](https://docs.python.org/3/whatsnew/3.0.html#builtins) (4th bullet down)  
- [How to force rounding technique](https://stackoverflow.com/a/10826537/4607272)
