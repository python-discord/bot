---
embed:
    title: "SQL & f-strings"
---
Don't use f-strings (`f""`) or other forms of "string interpolation" (`%`, `+`, `.format`) to inject data into a SQL query. It is an endless source of bugs and syntax errors. Additionally, in user-facing applications, it presents a major security risk via SQL injection.

Your database library should support "query parameters". A query parameter is a placeholder that you put in the SQL query. When the query is executed, you provide data to the database library, and the library inserts the data into the query for you, **safely**.

For example, the sqlite3 package supports using `?` as a placeholder:
```py
query = "SELECT * FROM stocks WHERE symbol = ?;"
params = ("RHAT",)
db.execute(query, params)
```
Note: Different database libraries support different placeholder styles, e.g. `%s` and `$1`. Consult your library's documentation for details.

**See Also**
- [Python sqlite3 docs](https://docs.python.org/3/library/sqlite3.html#how-to-use-placeholders-to-bind-values-in-sql-queries) - How to use placeholders to bind values in SQL queries
- [PEP-249](https://peps.python.org/pep-0249/) - A specification of how database libraries in Python should work
