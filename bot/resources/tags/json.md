JSON is a very handy way of storing values. But when starting out with JSON, you might run into the following error.

`JSONDecodeError: Expecting value: line 1 column 1 (char 0)`

What this error means is that the decoder (the reading of the JSON file) is expecting a character on line 1 column 1. In other words, your JSON is missing a critical character at the start. So it's saying that your JSON is invalid.
Looking at how JSON is set up, you can see that they require the following at minimum if you want to start out.

```json
{


}
```

If you add at least this to your JSON file, it should work. Make sure to put all your data between the `{}`, just like you would when making a dictionary.
