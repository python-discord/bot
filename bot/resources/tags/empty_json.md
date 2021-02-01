When creating a new JSON file you might run into the following error.

`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`

In short, this means that your JSON is invalid in its current state. This could very well happen because the file is just new and empty.
A JSON may never be completely empty. It is recommended to have at least one of the following in your json:

```
object
array
```

To resolve this issue, you create one of the above values in your JSON. It is very common to use `{}` to make an object, which is similar to a dictionary in python.
When this is added to your JSON, it will look like this:

```json
{

}
```

The error is resolved now.
Make sure to put all your data between the `{}`, just like you would when making a dictionary.
