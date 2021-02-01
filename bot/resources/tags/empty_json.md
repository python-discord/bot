When creating a new JSON file you might run into the following error.

`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`

In short, this means that your JSON is invalid in its current state. This could very well happen because the file is just new and completely empty.
Whilst the JSON data may be empty, the .json file must not. It is recommended to have at least one of the following data types in your .json file:

```
object
array
```

To resolve this issue, you create one of the above data types in your .json file. It is very common to use `{}` to make an object, which works similar to a dictionary in python.
When this is added to your .json file, it will look like this:

```json
{

}
```

The error is resolved now.
Make sure to put all your data between the `{}`, just like you would when making a dictionary.
