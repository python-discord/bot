---
embed:
    title: "Sending images in embeds using discord.py"
---
Thanks to discord.py, sending local files as embed images is simple. You have to create an instance of [`discord.File`](https://discordpy.readthedocs.io/en/stable/api.html#discord.File) class:
```py
# When you know the file exact path, you can pass it.
file = discord.File("/this/is/path/to/my/file.png", filename="file.png")

# When you have the file-like object, then you can pass this instead path.
with open("/this/is/path/to/my/file.png", "rb") as f:
    file = discord.File(f)
```
When using the file-like object, you have to open it in `rb` ('read binary') mode. Also, in this case, passing `filename` to it is not necessary.
Please note that `filename` must not contain underscores. This is a Discord limitation.

[`discord.Embed`](https://discordpy.readthedocs.io/en/stable/api.html#discord.Embed) instances have a [`set_image`](https://discordpy.readthedocs.io/en/stable/api.html#discord.Embed.set_image) method which can be used to set an attachment as an image:
```py
embed = discord.Embed()
# Set other fields
embed.set_image(url="attachment://file.png")  # Filename here must be exactly same as attachment filename.
```
After this, you can send an embed with an attachment to Discord:
```py
await channel.send(file=file, embed=embed)
```
This example uses [`discord.TextChannel`](https://discordpy.readthedocs.io/en/stable/api.html#discord.TextChannel) for sending, but any instance of [`discord.abc.Messageable`](https://discordpy.readthedocs.io/en/stable/api.html#discord.abc.Messageable) can be used for sending.
