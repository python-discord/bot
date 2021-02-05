When using JSON you might run into the following error:
```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```
This error could have appeared because you just created the JSON file and there is nothing in it at the moment.

Whilst having the data empty is no problem, the file itself may never be completely empty.

You most likely wanted to structure your JSON as a dictionary. For this change your JSON file to read `{}`.

Different data types are also supported. If you wish to read more on these, please reffer to the following article: https://www.tutorialspoint.com/json/json_data_types.htm
