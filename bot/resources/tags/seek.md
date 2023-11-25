---
embed:
    title: "Seek"
---
In the context of a [file object](https://docs.python.org/3/glossary.html#term-file-object), the `seek` function changes the stream position to a given byte offset, with an optional argument of where to offset from. While you can find the official documentation [here](https://docs.python.org/3/library/io.html#io.IOBase.seek), it can be unclear how to actually use this feature, so keep reading to see examples on how to use it.

File named `example`:
```
foobar
spam eggs
```
Open file for reading in byte mode:
```py
f = open('example', 'rb')
```
Note that stream positions start from 0 in much the same way that the index for a list does. If we do `f.seek(3, 0)`, our stream position will move 3 bytes forward relative to the **beginning** of the stream. Now if we then did `f.read(1)` to read a single byte from where we are in the stream, it would return the string `'b'` from the 'b' in 'foobar'. Notice that the 'b' is the 4th character. Also note that after we did `f.read(1)`, we moved the stream position again 1 byte forward relative to the **current** position in the stream. So the stream position is now currently at position 4.

Now lets do `f.seek(4, 1)`. This will move our stream position 4 bytes forward relative to our **current** position in the stream. Now if we did `f.read(1)`, it would return the string `'p'` from the 'p' in 'spam' on the next line. Note this time that the character at position 6 is the newline character `'\n'`.

Finally, lets do `f.seek(-4, 2)`, moving our stream position *backwards* 4 bytes relative to the **end** of the stream. Now if we did `f.read()` to read everything after our position in the file, it would return the string `'eggs'` and also move our stream position to the end of the file.

**Note**  
- For the second argument in `seek()`, use `os.SEEK_SET`, `os.SEEK_CUR`, and `os.SEEK_END` in place of 0, 1, and 2 respectively.  
- `os.SEEK_CUR` is only usable when the file is in byte mode.
