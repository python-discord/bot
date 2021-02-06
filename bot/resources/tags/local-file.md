Thanks to discord.py, sending local files as embed images is simple. You have to create an instance of `discord.File` class:
```py
# When you know the file exact path, you can pass it.
file = discord.File("/this/is/path/to/my/file.png", filename="file.png")

# When you have the file-like object, then you can pass this instead path.
with open("/this/is/path/to/my/file.png", "rb") as f:
    file = discord.File(f)
```
When using the file-like object, you have to open it in `rb` mode. Also, in this case, passing filename to it is not necessary.
Please note that `filename` can't contain underscores. This is Discord limitation.

`discord.Embed` instance has method `set_image` what can be used to set attachment as image:
```py
embed = discord.Embed()
# Set other fields
embed.set_image("attachment://file.png")  # Filename here must be exactly same as attachment filename.
```
After this, you can send embed and attachment to Discord:
```py
await channel.send(file=file, embed=embed)
```
This example uses `discord.TextChannel` for sending, but any `discord.Messageable` can be used for sending.

