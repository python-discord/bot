# ModLog

> Auto-generated documentation for [bot.cogs.moderation.modlog](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py) module.

- [Index](../../../README.md#modules) / [Bot](../../index.md#bot) / `Cogs` / [Moderation](index.md#moderation) / ModLog
  - [ModLog](#modlog)
    - [ModLog().ignore](#modlogignore)
    - [ModLog().on_guild_channel_create](#modlogon_guild_channel_create)
    - [ModLog().on_guild_channel_delete](#modlogon_guild_channel_delete)
    - [ModLog().on_guild_channel_update](#modlogon_guild_channel_update)
    - [ModLog().on_guild_role_create](#modlogon_guild_role_create)
    - [ModLog().on_guild_role_delete](#modlogon_guild_role_delete)
    - [ModLog().on_guild_role_update](#modlogon_guild_role_update)
    - [ModLog().on_guild_update](#modlogon_guild_update)
    - [ModLog().on_member_ban](#modlogon_member_ban)
    - [ModLog().on_member_join](#modlogon_member_join)
    - [ModLog().on_member_remove](#modlogon_member_remove)
    - [ModLog().on_member_unban](#modlogon_member_unban)
    - [ModLog().on_member_update](#modlogon_member_update)
    - [ModLog().on_message_delete](#modlogon_message_delete)
    - [ModLog().on_message_edit](#modlogon_message_edit)
    - [ModLog().on_raw_message_delete](#modlogon_raw_message_delete)
    - [ModLog().on_raw_message_edit](#modlogon_raw_message_edit)
    - [ModLog().send_log_message](#modlogsend_log_message)
    - [ModLog().upload_log](#modlogupload_log)

## ModLog

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L27)

```python
class ModLog(bot: Bot)
```

Logging for server events and staff actions.

### ModLog().ignore

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L65)

```python
def ignore(event: Event, items: int) -> None
```

Add event to ignored events to suppress log emission.

#### See also

- [Event](../../constants.md#event)

### ModLog().on_guild_channel_create

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L119)

```python
def on_guild_channel_create(
    channel: Union[discord.channel.CategoryChannel, discord.channel.TextChannel, discord.channel.VoiceChannel],
) -> None
```

Log channel create event to mod log.

### ModLog().on_guild_channel_delete

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L145)

```python
def on_guild_channel_delete(
    channel: Union[discord.channel.CategoryChannel, discord.channel.TextChannel, discord.channel.VoiceChannel],
) -> None
```

Log channel delete event to mod log.

### ModLog().on_guild_channel_update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L168)

```python
def on_guild_channel_update(
    before: Union[discord.channel.CategoryChannel, discord.channel.TextChannel, discord.channel.VoiceChannel],
    after: GuildChannel,
) -> None
```

Log channel update event to mod log.

### ModLog().on_guild_role_create

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L228)

```python
def on_guild_role_create(role: Role) -> None
```

Log role create event to mod log.

### ModLog().on_guild_role_delete

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L239)

```python
def on_guild_role_delete(role: Role) -> None
```

Log role delete event to mod log.

### ModLog().on_guild_role_update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L250)

```python
def on_guild_role_update(before: Role, after: Role) -> None
```

Log role update event to mod log.

### ModLog().on_guild_update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L303)

```python
def on_guild_update(before: Guild, after: Guild) -> None
```

Log guild update event to mod log.

### ModLog().on_member_ban

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L354)

```python
def on_member_ban(
    guild: Guild,
    member: Union[discord.member.Member, discord.user.User],
) -> None
```

Log ban event to user log.

### ModLog().on_member_join

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L371)

```python
def on_member_join(member: Member) -> None
```

Log member join event to user log.

### ModLog().on_member_remove

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L393)

```python
def on_member_remove(member: Member) -> None
```

Log member leave event to user log.

### ModLog().on_member_unban

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L410)

```python
def on_member_unban(guild: Guild, member: User) -> None
```

Log member unban event to mod log.

### ModLog().on_member_update

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L427)

```python
def on_member_update(before: Member, after: Member) -> None
```

Log member update event to user log.

### ModLog().on_message_delete

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L523)

```python
def on_message_delete(message: Message) -> None
```

Log message delete event to message change log.

### ModLog().on_message_edit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L620)

```python
def on_message_edit(before: Message, after: Message) -> None
```

Log message edit event to message change log.

### ModLog().on_raw_message_delete

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L579)

```python
def on_raw_message_delete(event: RawMessageDeleteEvent) -> None
```

Log raw message delete event to message change log.

### ModLog().on_raw_message_edit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L695)

```python
def on_raw_message_edit(event: RawMessageUpdateEvent) -> None
```

Log raw message edit event to message change log.

### ModLog().send_log_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L71)

```python
def send_log_message(
    icon_url: Union[str, NoneType],
    colour: Union[discord.colour.Colour, int],
    title: Union[str, NoneType],
    text: str,
    thumbnail: Union[str, discord.asset.Asset, NoneType] = None,
    channel_id: int = 282638479504965634,
    ping_everyone: bool = False,
    files: Union[List[discord.file.File], NoneType] = None,
    content: Union[str, NoneType] = None,
    additional_embeds: Union[List[discord.embeds.Embed], NoneType] = None,
    additional_embeds_msg: Union[str, NoneType] = None,
    timestamp_override: Union[datetime.datetime, NoneType] = None,
    footer: Union[str, NoneType] = None,
) -> Context
```

Generate log embed and send to logging channel.

### ModLog().upload_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/modlog.py#L37)

```python
def upload_log(messages: List[discord.message.Message], actor_id: int) -> str
```

Uploads the log data to the database via an API endpoint for uploading logs.

Used in several mod log embeds.

Returns a URL that can be used to view the log.
