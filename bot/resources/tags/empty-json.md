---
embed:
    title: "Empty JSON error"
---
When using JSON, you might run into the following error:
```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```
This error could have appeared because you just created the JSON file and there is nothing in it at the moment.

Whilst having empty data is no problem, the file itself may never be completely empty.

You most likely wanted to structure your JSON as a dictionary. To do this, edit your empty JSON file so that it instead contains `{}`.

Different data types are also supported. If you wish to read more on these, please refer to [this article](https://www.tutorialspoint.com/json/json_data_types.htm).
