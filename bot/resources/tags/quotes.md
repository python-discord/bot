---
embed:
    title: "String quotes"
---
Single and Double quoted strings are the **same** in Python. The choice of which one to use is up to you, just make sure that you **stick to that choice**.

With that said, there are exceptions to this that are more important than consistency. If a single or double quote is needed *inside* the string, using the opposite quotation is better than using escape characters.

Example:
```py
'My name is "Guido"'   # good
"My name is \"Guido\"" # bad

"Don't go in there"  # good
'Don\'t go in there' # bad
```
**Note:**
If you need both single and double quotes inside your string, use the version that would result in the least amount of escapes. In the case of a tie, use the quotation you use the most.

**References:**  
- [pep-8 on quotes](https://peps.python.org/pep-0008/#string-quotes)  
- [convention for triple quoted strings](https://peps.python.org/pep-0257/)
