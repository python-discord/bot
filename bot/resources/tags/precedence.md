---
embed:
    title: "Operator precedence"
---
Operator precedence is essentially like an order of operations for Python's operators.

**Example 1** (arithmetic)
`2 * 3 + 1` is `7` because multiplication is first
`2 * (3 + 1)` is `8` because the parenthesis change the precedence allowing the sum to be first

**Example 2** (logic)
`not True or True` is `True` because the `not` is first
`not (True or True)` is `False` because the `or` is first

The full table of precedence from lowest to highest is [here](https://docs.python.org/3/reference/expressions.html#operator-precedence)
