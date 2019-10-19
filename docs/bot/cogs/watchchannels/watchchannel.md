# WatchChannel

> Auto-generated documentation for [bot.cogs.watchchannels.watchchannel](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py) module.

- [Index](../../../README.md#modules) / [Bot](../../index.md#bot) / `Cogs` / [Watchchannels](index.md#watchchannels) / WatchChannel
  - [MessageHistory](#messagehistory)
  - [WatchChannel](#watchchannel)
    - [WatchChannel().consuming_messages](#watchchannelconsuming_messages)
    - [WatchChannel().modlog](#watchchannelmodlog)
    - [WatchChannel().cog_unload](#watchchannelcog_unload)
    - [WatchChannel().consume_messages](#watchchannelconsume_messages)
    - [WatchChannel().fetch_user_cache](#watchchannelfetch_user_cache)
    - [WatchChannel().list_watched_users](#watchchannellist_watched_users)
    - [WatchChannel().on_message](#watchchannelon_message)
    - [WatchChannel().relay_message](#watchchannelrelay_message)
    - [WatchChannel().send_header](#watchchannelsend_header)
    - [WatchChannel().start_watchchannel](#watchchannelstart_watchchannel)
    - [WatchChannel().webhook_send](#watchchannelwebhook_send)
  - [proxy_user](#proxy_user)

## MessageHistory

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L44)

```python
class MessageHistory(
    last_author: Union[int, NoneType] = None,
    last_channel: Union[int, NoneType] = None,
    message_count: int = 0,
) -> None
```

Represents a watch channel's message history.

## WatchChannel

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L52)

```python
class WatchChannel(
    bot: Bot,
    destination: int,
    webhook_id: int,
    api_endpoint: str,
    api_default_params: dict,
    logger: <MagicMock id='140270945482344'>,
) -> None
```

ABC with functionality for relaying users' messages to a certain channel.

### WatchChannel().consuming_messages

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L52)

```python
#property getter
def consuming_messages() -> bool
```

Checks if a consumption task is currently running.

### WatchChannel().modlog

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L52)

```python
#property getter
def modlog() -> ModLog
```

Provides access to the ModLog cog for alert purposes.

### WatchChannel().cog_unload

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L335)

```python
def cog_unload() -> None
```

Takes care of unloading the cog and canceling the consumption task.

### WatchChannel().consume_messages

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L185)

```python
def consume_messages(delay_consumption: bool = True) -> None
```

Consumes the message queues to log watched users' messages.

### WatchChannel().fetch_user_cache

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L155)

```python
def fetch_user_cache() -> bool
```

Fetches watched users from the API and updates the watched user cache accordingly.

This function returns `True` if the update succeeded.

### WatchChannel().list_watched_users

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L296)

```python
def list_watched_users(ctx: Context, update_cache: bool = True) -> None
```

Gives an overview of the watched user list for this channel.

The optional kwarg `update_cache` specifies whether the cache should
be refreshed by polling the API.

### WatchChannel().on_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L175)

```python
def on_message(msg: Message) -> None
```

Queues up messages sent by watched users.

### WatchChannel().relay_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L230)

```python
def relay_message(msg: Message) -> None
```

Relays the message to the relevant watch channel.

### WatchChannel().send_header

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L278)

```python
def send_header(msg: Message) -> None
```

Sends a header embed with information about the relayed messages to the watch channel.

### WatchChannel().start_watchchannel

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L107)

```python
def start_watchchannel() -> None
```

Starts the watch channel by getting the channel, webhook, and user cache ready.

### WatchChannel().webhook_send

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L214)

```python
def webhook_send(
    content: Union[str, NoneType] = None,
    username: Union[str, NoneType] = None,
    avatar_url: Union[str, NoneType] = None,
    embed: Union[discord.embeds.Embed, NoneType] = None,
) -> None
```

Sends a message to the webhook with the specified kwargs.

## proxy_user

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/watchchannels/watchchannel.py#L27)

```python
def proxy_user(user_id: str) -> Object
```

A proxy user object that mocks a real User instance for when the later is not available.
