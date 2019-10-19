# Utils

> Auto-generated documentation for [bot.cogs.moderation.utils](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/utils.py) module.

- [Index](../../../README.md#modules) / [Bot](../../index.md#bot) / `Cogs` / [Moderation](index.md#moderation) / Utils
  - [has_active_infraction](#has_active_infraction)
  - [notify_infraction](#notify_infraction)
  - [notify_pardon](#notify_pardon)
  - [post_infraction](#post_infraction)
  - [proxy_user](#proxy_user)
  - [send_private_embed](#send_private_embed)

## has_active_infraction

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/utils.py#L92)

```python
def has_active_infraction(
    ctx: Context,
    user: Union[discord.member.Member, discord.user.User, discord.object.Object],
    infr_type: str,
) -> bool
```

Checks if a user already has an active infraction of the given type.

## notify_infraction

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/utils.py#L112)

```python
def notify_infraction(
    user: Union[discord.member.Member, discord.user.User],
    infr_type: str,
    expires_at: Union[str, NoneType] = None,
    reason: Union[str, NoneType] = None,
    icon_url: str = 'https://cdn.discordapp.com/emojis/470326273298792469.png',
) -> bool
```

DM a user about their new infraction and return True if the DM is successful.

## notify_pardon

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/utils.py#L141)

```python
def notify_pardon(
    user: Union[discord.member.Member, discord.user.User],
    title: str,
    content: str,
    icon_url: str = 'https://cdn.discordapp.com/emojis/470326274519334936.png',
) -> bool
```

DM a user about their pardoned infraction and return True if the DM is successful.

## post_infraction

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/utils.py#L51)

```python
def post_infraction(
    ctx: Context,
    user: Union[discord.member.Member, discord.user.User, discord.object.Object],
    infr_type: str,
    reason: str,
    expires_at: datetime = None,
    hidden: bool = False,
    active: bool = True,
) -> Union[dict, NoneType]
```

Posts an infraction to the API.

## proxy_user

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/utils.py#L33)

```python
def proxy_user(user_id: str) -> Object
```

Create a proxy user object from the given id.

Used when a Member or User object cannot be resolved.

## send_private_embed

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/moderation/utils.py#L158)

```python
def send_private_embed(
    user: Union[discord.member.Member, discord.user.User],
    embed: Embed,
) -> bool
```

A helper method for sending an embed to a user's DMs.

Returns a boolean indicator of DM success.
