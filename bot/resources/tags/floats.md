**Floating Point Arithmetic**
You may have noticed that when doing arithmetic with floats in Python you sometimes get strange results, like this:
```python
>>> 0.1 + 0.2
0.30000000000000004
```
**Why this happens**
Internally your computer stores floats as as binary fractions. Many decimal values cannot be stored as exact binary fractions, which means an approximation has to be used.

**How you can avoid this**
If you require an exact decimal representation, you can use the [decimal](https://docs.python.org/3/library/decimal.html) or [fractions](https://docs.python.org/3/library/fractions.html) module. Here is an example using the decimal module:
```python
>>> from decimal import Decimal
>>> Decimal('0.1') + Decimal('0.2')
Decimal('0.3')
```
Note that we enter in the number we want as a string so we don't pass on the imprecision from the float.

For more details on why this happens check out this [page in the python docs](https://docs.python.org/3/tutorial/floatingpoint.html) or this [Computerphile video](https://www.youtube.com/watch/PZRI1IfStY0).
