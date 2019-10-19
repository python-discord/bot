# AntiSpam

> Auto-generated documentation for [bot.cogs.antispam](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / AntiSpam
  - [AntiSpam](#antispam)
    - [AntiSpam().mod_log](#antispammod_log)
    - [AntiSpam().alert_on_validation_error](#antispamalert_on_validation_error)
    - [AntiSpam().maybe_delete_messages](#antispammaybe_delete_messages)
    - [AntiSpam().on_message](#antispamon_message)
    - [AntiSpam().punish](#antispampunish)
  - [DeletionContext](#deletioncontext)
    - [DeletionContext().add](#deletioncontextadd)
    - [DeletionContext().upload_messages](#deletioncontextupload_messages)
  - [setup](#setup)
  - [validate_config](#validate_config)

## AntiSpam

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L97)

```python
class AntiSpam(bot: Bot, validation_errors: bool) -> None
```

Cog that controls our anti-spam measures.

### AntiSpam().mod_log

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L97)

```python
#property getter
def mod_log() -> ModLog
```

Allows for easy access of the ModLog cog.

### AntiSpam().alert_on_validation_error

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L117)

```python
def alert_on_validation_error() -> None
```

Unloads the cog and alerts admins if configuration validation failed.

### AntiSpam().maybe_delete_messages

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L226)

```python
def maybe_delete_messages(
    channel: TextChannel,
    messages: List[discord.message.Message],
) -> None
```

Cleans the messages if cleaning is configured.

### AntiSpam().on_message

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L136)

```python
def on_message(message: Message) -> None
```

Applies the antispam rules to each received message.

### AntiSpam().punish

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L207)

```python
def punish(msg: Message, member: Member, reason: str) -> None
```

Punishes the given member for triggering an antispam rule.

## DeletionContext

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L40)

```python
class DeletionContext(
    channel: TextChannel,
    members: Dict[int, discord.member.Member] = <factory>,
    rules: Set[str] = <factory>,
    messages: Dict[int, discord.message.Message] = <factory>,
) -> None
```

Represents a Deletion Context for a single spam event.

### DeletionContext().add

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L48)

```python
def add(
    rule_name: str,
    members: Iterable[discord.member.Member],
    messages: Iterable[discord.message.Message],
) -> None
```

Adds new rule violation events to the deletion context.

### DeletionContext().upload_messages

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L60)

```python
def upload_messages(actor_id: int, modlog: ModLog) -> None
```

Method that takes care of uploading the queue and posting modlog alert.

#### See also

- [ModLog](moderation/modlog.md#modlog)

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L278)

```python
def setup(bot: Bot) -> None
```

Antispam cog load.

## validate_config

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/antispam.py#L257)

```python
def validate_config(
    rules: Mapping = {'attachments': {'interval': 10, 'max': 9}, 'burst': {'interval': 10, 'max': 7}, 'burst_shared': {'interval': 10, 'max': 20}, 'chars': {'interval': 5, 'max': 3000}, 'duplicates': {'interval': 10, 'max': 3}, 'discord_emojis': {'interval': 10, 'max': 20}, 'links': {'interval': 10, 'max': 10}, 'mentions': {'interval': 10, 'max': 5}, 'newlines': {'interval': 10, 'max': 100, 'max_consecutive': 10}, 'role_mentions': {'interval': 10, 'max': 3}},
) -> Dict[str, str]
```

Validates the antispam configs.
