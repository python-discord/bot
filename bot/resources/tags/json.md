When creating a new JSON file you might run into the following error.

`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`

In short this error means your JSON is invalid in it's current state.
A JSON may never be completely empty and must always at least have one of the following items.

```
object
array
string
number
"true"
"false"
"null"
```

To resolve this issue, you create one of the above values in your JSON. It is very common to use `{}` to make an object. Adding the following to your JSON should resolve this issue.

```json
{


}
```

Make sure to put all your data between the `{}`, just like you would when making a dictionary.
