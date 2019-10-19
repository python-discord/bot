# Messages

> Auto-generated documentation for [bot.utils.messages](https://github.com/python-discord/bot/blob/master/bot/utils/messages.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Utils](index.md#utils) / Messages
  - [send_attachments](#send_attachments)
  - [wait_for_deletion](#wait_for_deletion)

## send_attachments

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/messages.py#L54)

```python
def send_attachments(
    message: Message,
    destination: Union[discord.channel.TextChannel, discord.webhook.Webhook],
) -> None
```

Re-uploads each attachment in a message to the given channel or webhook.

Each attachment is sent as a separate message to more easily comply with the 8 MiB request size limit.
If attachments are too large, they are instead grouped into a single embed which links to them.

## wait_for_deletion

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/messages.py#L15)

```python
def wait_for_deletion(
    message: Message,
    user_ids: Sequence[discord.abc.Snowflake],
    deletion_emojis: Sequence[str] = ('❌',),
    timeout: float = 300,
    attach_emojis: bool = True,
    client: Union[discord.client.Client, NoneType] = None,
) -> None
```

Wait for up to `timeout` seconds for a reaction by any of the specified `user_ids` to delete the message.

An `attach_emojis` bool may be specified to determine whether to attach the given
`deletion_emojis` to the message in the given `context`

A `client` instance may be optionally specified, otherwise client will be taken from the
guild of the message.
