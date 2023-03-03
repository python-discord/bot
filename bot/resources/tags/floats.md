---
embed:
    title: "Floating point arithmetic"
---
You may have noticed that when doing arithmetic with floats in Python you sometimes get strange results, like this:
```python
>>> 0.1 + 0.2
0.30000000000000004
```
**Why this happens**
Internally your computer stores floats as binary fractions. Many decimal values cannot be stored as exact binary fractions, which means an approximation has to be used.

**How you can avoid this**
 You can use [math.isclose](https://docs.python.org/3/library/math.html#math.isclose) to check if two floats are close, or to get an exact decimal representation, you can use the [decimal](https://docs.python.org/3/library/decimal.html) or [fractions](https://docs.python.org/3/library/fractions.html) module. Here are some examples:
```python
>>> math.isclose(0.1 + 0.2, 0.3)
True
>>> decimal.Decimal('0.1') + decimal.Decimal('0.2')
Decimal('0.3')
```
Note that with `decimal.Decimal` we enter the number we want as a string so we don't pass on the imprecision from the float.

For more details on why this happens check out this [page in the python docs](https://docs.python.org/3/tutorial/floatingpoint.html) or this [Computerphile video](https://www.youtube.com/watch/PZRI1IfStY0).
